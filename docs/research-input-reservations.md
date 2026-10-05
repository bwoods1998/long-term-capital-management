The isolated research broker's input count can be a conservative billing ceiling
for the entire reviewed service window. It need not equal the tokens in the actual
prompt. The Sail host adapter deliberately returns its reviewed
`billable_input_ceiling` after checking the complete request's byte limit.

Sail [publishes 1M context windows](https://docs.sailresearch.com/models) for the
configured DeepSeek V4 Flash and Pro models. Reserving 1,048,576 uncached input
tokens conservatively covers both decimal and binary interpretations of that
label. This does not assert that 1,048,576 input tokens can actually be sent.
The generic ModelPolicy validator permits that input reservation while retaining
its 1,000,000 output ceiling. Each reviewed profile still supplies its own tighter
input and output limits, efforts, tools, prices and validity interval.

Sail's [native context admission](https://docs.sailresearch.com/support#cross-api-behavior)
requires actual input plus requested output to fit the model window after its
formatting allowance. The existing host wire preserves text input, tools,
requested maximum output, reasoning effort and disabled truncation; it adds no
raw-token override. The larger billing reservation changes none of those fields
and does not bypass native admission.

The current actor configuration still uses flash_asap/minimal/8000 and
flash41_asap/minimal/8000 for ordinary and long-history research,
pro_asap/medium/12000 and k3_balanced/medium/12000 for rewrites, and
pro_asap/high/32000 for the architect. Their profile-to-model definitions remain
unchanged. The existing host bridge's foreground-asap restriction remains a
separate constraint on a balanced profile; the input ceiling does not convert
completion windows or substitute models.

For a synthetic Flash fixture at the observed base rates of $0.09 input and $0.18
output per million, a whole-window reservation plus 8000 requested output tokens
holds $0.09581184 even when the request contains only a short prompt. That is a
conditional arithmetic example. Public prices are not an inclusive tax or future
price guarantee and do not open paid admission. The shared daily budget, original
pending liabilities and all real authority checks still govern dispatch.

The old private whole-context calculator also contains a 1,000,000 input guard.
That immutable helper needs a separately reviewed new revision if reused; changing
the public validator does not rewrite or relabel its historical preparation.
