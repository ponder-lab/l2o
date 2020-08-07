import os
import json
import pprint

import tensorflow as tf

import l2o


def load(folder):
    return l2o.train.build_from_config(os.path.join(folder, "config.json"))


if __name__ == '__main__':

    import sys
    folder = sys.argv[1]
    stage = sys.argv[2]
    period = sys.argv[3]

    strategy = load(folder)
    strategy.evaluate(int(stage), int(period))
