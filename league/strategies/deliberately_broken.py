import os

NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "broken", "symbols": ["BTC/USD"]}
PARAMS = {}


def decide(ctx):
    return {"intents": [], "thought": os.getcwd()}
