import os
import functools

import tensorflow as tf
import numpy as np
import pandas as pd

from l2o import problems


def _makedir(path, assert_empty=False):
    """Helper function to create a directory"""
    if os.path.isdir(path):
        if assert_empty:
            raise Exception(
                path, "Directory {} already exists; please rename or "
                "delete the directory.".format(path))
    else:
        os.mkdir(path)


def _mean_loss(results):
    """Helper function to compute mean loss."""
    return np.mean([
        np.mean([np.mean(loss_array) for loss_array in result.loss])
        for result in results
    ])


def _deserialize_problem(p):
    """Helper function to deserialize a problem into a ProblemSpec."""
    if isinstance(p, problems.ProblemSpec):
        return p
    else:
        try:
            target, args, kwargs = p
            if type(target) == str:
                target = getattr(problems, target)
            return problems.ProblemSpec(target, args, kwargs)
        except Exception as e:
            raise TypeError(
                "Problem could not be deserialized: {}\n{}".format(p, e))


class BaseStrategy:
    """Base Class for training strategies

    Parameters
    ----------
    learner : optimizer.TrainableOptimizer
        Optimizer to train

    Keyword Args
    ------------
    train_args : dict
        Arguments to pass to ``train``.
    problems : problems.ProblemSpec[]
        List of problem specifications to train on
    epochs_per_period : int
        Number of meta-epochs to train per training 'period'
    optimizer : tf.keras.optimizers.Optimizer or str or dict
        Optimizer to train learned optimizer with; initialized with
        tf.keras.optimizers.get to support str and dict formats.
    directory : str
        Directory to save weights and other data to

    Attributes
    ----------
    COLUMNS : dict
        Dict containing summary keys and data types; should be overridden
    """

    COLUMNS = {}

    def __init__(
            self, learner, name="GenericStrategy", train_args={}, problems=[],
            epochs_per_period=10,
            optimizer="Adam", directory="weights"):

        self.problems = [_deserialize_problem(p) for p in problems]

        self.learner = learner
        self.optimizer = tf.keras.optimizers.get(optimizer)
        self.train_args = train_args

        self.epochs_per_period = epochs_per_period

        self.name = name
        self.directory = directory
        _makedir(self.directory)

        try:
            self.summary = pd.read_csv(
                os.path.join(self.directory, "summary.csv"))
            self._resume()
        except FileNotFoundError:
            self.summary = pd.DataFrame({
                k: pd.Series([], dtype=v) for k, v in self.COLUMNS.items()})
            self._start()

    def __repr__(self):
        return "<{} training {}:{} @ {}>".format(
            self.name, self.learner.name,
            self.learner.network.name, self.directory)

    def _path(self, *args, **kwargs):
        """Get saved model file path"""
        raise NotImplementedError()

    def _resume(self):
        """Resume current optimization."""
        raise NotImplementedError()

    def _start(self):
        """Start new optimization."""
        raise NotImplementedError()

    def _append(self, **kwargs):
        """Append to summary statistics"""
        self.summary = self.summary.append(
            pd.DataFrame({k: [v] for k, v in kwargs.items()}),
            ignore_index=True)
        self.summary.to_csv(
            os.path.join(self.directory, "summary.csv"), index=False)

    def _lookup(self, **kwargs):
        """Helper function to look up values from dataframe"""
        try:
            filtered = self.summary
            for k, v in kwargs.items():
                filtered = filtered[filtered[k] == v]
            return filtered.iloc[0]
        except IndexError:
            return None

    def _load_network(self, *args, **kwargs):
        """Helper function to load network weights"""
        path = self._path(*args, **kwargs)
        self.learner.network.load_weights(path)
        print("Loaded weights: {}".format(path))

    def _save_network(self, *args, **kwargs):
        """Helper function to save network weights"""
        path = self._path(*args, **kwargs)
        _makedir(os.path.dirname(path))
        self.learner.save(path)
        print("Saved weights: {}".format(path))

    def _learning_period(self, train_args, validation_args):
        """Trains for ``epochs_per_period`` meta-epochs.

        Parameters
        ----------
        train_args : dict
            Arguments to pass to self.learner.train
        validation_args : dict
            Arguments to pass to self.learner.train when validate=True

        Returns
        -------
        [float, float]
            [0] Training loss
            [1] Validation loss
        """

        # Bind common arguments; functools.partial can be overridden
        train_func = functools.partial(
            self.learner.train,
            self.problems, self.optimizer, **self.train_args)

        # Train for ``epochs_per_period`` meta-epochs
        training_loss = []
        for i in range(self.epochs_per_period):
            print("Training: Epoch {}/{}".format(
                i + 1, self.epochs_per_period))
            training_loss.append(_mean_loss(
                train_func(validation=False, **train_args)))
        training_loss = np.mean(training_loss)

        # Compute validation loss
        print("Validating")
        validation_loss = _mean_loss(train_func(
            validation=True, **validation_args))

        print("training_loss: {} | validation_loss: {}".format(
            training_loss, validation_loss))

        return training_loss, validation_loss

    def train(self):
        """The actual training method."""
        raise NotImplementedError()