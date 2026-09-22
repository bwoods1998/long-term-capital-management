# Read-only extraction of the semantic lab's completed market labels and quotes (runs on the House box).
import sqlite3,json,gzip,base64,sys,io,csv
part=sys.argv[1]
db=sqlite3.connect('file:/workspace/state/semantic.sqlite?mode=ro',uri=True)
K=['ambiguous_settlement','continuous_threshold','discrete_event','fragile_liquidity','missing_catalyst_context','recent_reversal','related_exposure','relative_return']
buf=io.StringIO(); w=csv.writer(buf)
if part=='tasks':
    cols=["entity","observed","finished","json_extract(body,'$.state.observed_minute')",
      "json_extract(body,'$.state.market.yes_bid')","json_extract(body,'$.state.market.yes_ask')",
      "json_extract(body,'$.state.market.open_interest')","json_extract(body,'$.state.market.hours_to_close')",
      "json_extract(body,'$.state.earlier_quotes[0].bid')","json_extract(body,'$.state.earlier_quotes[0].ask')",
      "json_extract(body,'$.state.market.series')","cost","json_extract(response,'$.usage.input_tokens')"]+[f"json_extract(response,'$.answers.{k}.noul')" for k in K]
    for r in db.execute(f"select {','.join(cols)} from semantic_tasks where kind='market' and status='completed'"):
        w.writerow(r)
else:
    for r in db.execute("select market,observed,bid,ask from semantic_quotes"):
        w.writerow(r)
print(base64.b64encode(gzip.compress(buf.getvalue().encode(),9)).decode())
