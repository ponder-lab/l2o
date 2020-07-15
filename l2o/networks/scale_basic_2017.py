import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import LSTMCell, Dense

from .moments import rms_scaling


class ScaleBasicOptimizer(tf.keras.Model):
    """RNN that operates on each coordinate independently, as specified by
    the scale paper.

    Keyword Args
    ------------
    layers : int[]
        Sizes of LSTM layers.
    init_lr : float | float[2]
        Learning rate initialization parameters. If ``float``, all parameter
        learning rates are initialized as a constant. If ``tuple``, the
        learning rates are initialized from a
        ``Normal(init_lr[0], init_lr[1])``.
    name : str
        Name of optimizer network.
    **kwargs : dict
        Passed onto tf.keras.layers.LSTMCell
    """

    def __init__(
            self, layers=(20, 20), init_lr=(1., 1.),
            name="ScaleBasicOptimizer", **kwargs):

        super().__init__(name=name)

        self.init_lr = init_lr

        self.recurrent = [LSTMCell(hsize, **kwargs) for hsize in layers]

        self.delta = Dense(1, input_shape=(layers[-1],))
        self.decay = Dense(1, input_shape=(layers[-1],), activation="sigmoid")
        self.learning_rate_change = Dense(
            1, input_shape=(layers[-1],), activation="sigmoid")

    def call(self, param, inputs, states):

        # Scaling
        grad, states["rms"] = rms_scaling(
            inputs, states["decay"], states["rms"])

        # Recurrent
        x = tf.reshape(grad, [-1, 1])
        for i, layer in enumerate(self.recurrent):
            hidden_name = "rnn_{}".format(i)
            x, states[hidden_name] = layer(x, states[hidden_name])

        # Update scaling hyperparameters
        states["decay"] = tf.reshape(self.decay(x), param.shape)
        states["learning_rate"] *= tf.reshape(
            2. * self.learning_rate_change(x), param.shape)
        update = tf.reshape(
            states["learning_rate"] * self.delta(x), param.shape)

        return update, states

    def get_initial_state(self, var):

        # RNN state
        batch_size = tf.size(var)
        rnn_state = {
            "rnn_{}".format(i): layer.get_initial_state(
                batch_size=batch_size, dtype=tf.float32)
            for i, layer in enumerate(self.recurrent)
        }

        # Learning rate random initialization
        if type(self.init_lr) == tuple:
            init_lr = tf.exp(tf.random.uniform(
                tf.shape(var),
                np.log(self.init_lr[0]),
                np.log(self.init_lr[1])))
        else:
            init_lr = tf.constant(self.init_lr, shape=tf.shape(var))

        # State for analytical computations
        analytical_state = {
            "rms": tf.zeros(tf.shape(var)),
            "learning_rate": init_lr,
            "decay": tf.zeros(tf.shape(var))
        }

        return dict(**rnn_state, **analytical_state)