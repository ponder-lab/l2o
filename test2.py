import l2o


default = l2o.train.get_default(
    loss="imitation", strategy="simple", network="dmoptimizer")
trainer = l2o.train.build_argv(default)
trainer.train()