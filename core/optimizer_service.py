from core.legacy_adapters.optimizer import optimize_symbol_light, run_batch_optimizer


def optimize_symbol(**kwargs):
    return optimize_symbol_light(**kwargs)


def optimize_leaders_batch():
    return run_batch_optimizer()
