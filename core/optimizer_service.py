from backtest_optimizer_light import optimize_symbol_light
from batch_optimize_leaders_light import run_batch_optimizer


def optimize_symbol(**kwargs):
    return optimize_symbol_light(**kwargs)


def optimize_leaders_batch():
    return run_batch_optimizer()
