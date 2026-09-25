# Read-only extended extraction of semantic lab market tasks (runs on the House box). args: part lo hi
import sqlite3,json,gzip,base64,sys,io,csv
part=sys.argv[1]
db=sqlite3.connect('file:/workspace/state/semantic.sqlite?mode=ro',uri=True)
K=['ambiguous_settlement','continuous_threshold','discrete_event','fragile_liquidity','missing_catalyst_context','recent_reversal','related_exposure','relative_return']
buf=io.StringIO(); w=csv.writer(buf)
if part=='tasks':
    lo,hi=int(sys.argv[2]),int(sys.argv[3])
    cols=["rowid","entity","observed","finished","json_extract(body,'$.state.observed_minute')",
      "json_extract(body,'$.state.market.yes_bid')","json_extract(body,'$.state.market.yes_ask')",
      "json_extract(body,'$.state.market.open_interest')","json_extract(body,'$.state.market.hours_to_close')",
      "json_extract(body,'$.state.earlier_quotes[0].bid')","json_extract(body,'$.state.earlier_quotes[0].ask')",
      "json_extract(body,'$.state.market.series')","cost","json_extract(response,'$.usage.input_tokens')",
      "json_extract(body,'$.state.market.volume_24h')","json_extract(body,'$.state.market.hours_to_resolve')",
      "json_extract(body,'$.state.market.strike')","json_extract(body,'$.state.market.title')",
      "json_array_length(json_extract(body,'$.state.peers'))","json_extract(body,'$.state.earlier_quotes')",
      "(select count(*) from json_each(json_extract(body,'$.questions')))",
      "length(coalesce(json_extract(body,'$.state.market.rules_primary'),''))",
      "json_extract(body,'$.state.market.subtitle')","json_extract(body,'$.state.market.close_time')",
      "started","json_extract(body,'$.model')"
      ]+[f"json_extract(response,'$.answers.{k}.noul')" for k in K]
    for r in db.execute(f"select {','.join(cols)} from semantic_tasks where kind='market' and status='completed' and rowid>=? and rowid<?",(lo,hi)):
        w.writerow(r)
else:
    for r in db.execute("select market,observed,bid,ask from semantic_quotes"):
        w.writerow(r)
print(base64.b64encode(gzip.compress(buf.getvalue().encode(),9)).decode())
