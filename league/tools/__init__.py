"""Helper modules Merton, as toolsmith, builds when agents ask for them (the tool-request queue).

A tool is pure Python under the same safety rules as a strategy, because it runs in the same
sealed boxes: the sandbox uploads this directory beside the strategy, and a strategy may
`from tools.<name> import ...`. Nothing here can reach a network, a file or the House.
"""
