"""Extended version of ChoiceOptimizer."""

import tensorflow as tf
from tensorflow.keras.layers import LSTMCell, Dense

from .rnnprop_2016 import RNNPropOptimizer
from .moments import rms_momentum
from .softmax import softmax


class ChoiceExtendedOptimizer(RNNPropOptimizer):
    """Extended version of ChoiceOptimizer, similar to RNNPropExtended."""

    default_name = "ChoiceExtended"

    def init_layers(
            self, layers=(20, 20), beta_1=0.9, beta_2=0.999,
            epsilon=1e-10, learning_rate=0.001, hardness=0.0, **kwargs):
        """Initialize Layers."""
        self.beta_1 = beta_1
        self.beta_2 = beta_2
        self.epsilon = epsilon

        self.hardness = hardness
        self.learning_rate = learning_rate

        self.recurrent = [LSTMCell(hsize, **kwargs) for hsize in layers]
        self.choice = Dense(3, input_shape=(layers[-1] + 3,))

    def call(self, param, inputs, states, global_state):
        """Policy call override."""
        # Momentum & Variance
        states_new = {}
        states_new["m"], states_new["v"] = rms_momentum(
            inputs, states["m"], states["v"],
            beta_1=self.beta_1, beta_2=self.beta_2)

        m_hat = states_new["m"] / (1. - self.beta_1)
        v_hat = states_new["v"] / (1. - self.beta_2)
        m_tilde = m_hat / tf.sqrt(v_hat + self.epsilon)
        g_tilde = inputs / tf.sqrt(v_hat + self.epsilon)

        # Recurrent
        inputs_augmented = tf.concat([
            tf.reshape(f, [-1, 1]) for f in [inputs, m_tilde, g_tilde]], 1)
        x = inputs_augmented
        for i, layer in enumerate(self.recurrent):
            hidden_name = "rnn_{}".format(i)
            x, states_new[hidden_name] = layer(x, states[hidden_name])
            x = tf.concat([x, inputs_augmented], 1)

        # Make choice
        opt_weights = softmax(
            tf.reshape(self.choice(x), [-1, 3]),
            hardness=self.hardness, train=self.train, epsilon=self.epsilon)

        # Combine softmax
        update = self.learning_rate * tf.math.reduce_sum(
            opt_weights * inputs_augmented, axis=1)

        return tf.reshape(update, tf.shape(param)), states_new