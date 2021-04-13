"""Outer Optimization Step."""

import tensorflow as tf
import time


class StepMixin:
    """Outer Optimization Step Mixin."""

    def _summarize(self, meta_loss, imitation_loss, states, callback_states):
        """Aggregate loss and summary statistics."""
        distribute = tf.distribute.get_strategy()
        summary = {
            "meta_loss": distribute.reduce(
                tf.distribute.ReduceOp.MEAN, meta_loss, axis=None),
            "imitation_loss": distribute.reduce(
                tf.distribute.ReduceOp.MEAN, imitation_loss, axis=None)
        }
        for st, cb in zip(callback_states, self.step_callbacks):
            summary.update(cb.summarize(st, distribute))

        return states, summary

    @tf.function
    def abstract_train_step(
            self, data, states, scale,
            meta_loss_weight=0.0, imitation_loss_weight=1.0, **kwargs):
        """Single outer step.

        Wraps abstract_loss to compute outer gradients inside outer-parallel
        graph; see ``abstract_loss`` for docstring.

        Keyword Args
        ------------
        meta_loss_weight : float
            Weight applied to meta loss. If 0, meta loss is not computed.
        imitation_loss_weight : float
            Weight applied to imitation loss. If 0, imitation loss is not
            computed.
        """
        def _get_loss(*args):
            d, s, c = args
            """Helper to compute inner loss."""
            results = self.abstract_loss(d, s, c, **kwargs)
            loss = (
                meta_loss_weight * results[0]
                + imitation_loss_weight * results[1])
            return results, loss

        def _inner(data_, states_, scale_):
            """Distribute function.

            Since ``data`` and ``params`` contain per-replica tensor values,
            they must be explicitly passed as parameters; then, since
            ``kwargs`` only contains bound constants, they are captured by
            closure instead of passed through ``distribute.run``.
            """
            # Noise step
            ptb = self.network.perturbation
            ptb.reset()
            for _ in range(ptb.adversarial_attack_steps):
                # We manually watch variables here since we only
                # want to watch perturbable_variables, not trainable_variables.
                with tf.GradientTape(watch_accessed_variables=False) as tape:
                    tape.watch(ptb.perturbable_variables)
                    results, loss = _get_loss(data_, states_, scale_)
                grads = tape.gradient(loss, ptb.perturbable_variables)
                ptb.apply_gradients(zip(ptb.perturbable_variables, grads))

            # Meta step
            with tf.GradientTape(watch_accessed_variables=False) as tape:
                tape.watch(self.network.trainable_variables)
                results, loss = _get_loss(data_, states_, scale_)
            grads = tape.gradient(loss, self.network.trainable_variables)

            clipped = self.gradient_clipping.clip(
                self.network.trainable_variables, grads)
            self.optimizer.apply_gradients(
                zip(clipped, self.network.trainable_variables))

            # Don't forget to reset after use!
            ptb.reset()

            return results

        distribute = tf.distribute.get_strategy()
        return self._summarize(
            *distribute.run(_inner, args=(data, states, scale)))

    @tf.function
    def abstract_valid_step(self, data, states, scale, **kwargs):
        """Single outer step (validation mode)."""

        def _inner(data_, states_, scale_):
            return self.abstract_loss(data_, states_, scale_, **kwargs)

        distribute = tf.distribute.get_strategy()
        return self._summarize(
            *distribute.run(_inner, args=(data, states, scale)))

    def make_concrete_step(self, meta, data, states, scale):
        """Get a concrete @tf.function graph for abstract_step.

        A concrete function is a single graph generated by AutoGraph; see
        ``https://www.tensorflow.org/guide/concrete_function``.

        In general, the rules are (as of 2.3.0-rc1):
          - Nested structures (lists, dicts of Tensors) must maintain the same
            internal values and dimensions
          - Python objects are 'bound' and must be constant (i.e. id())
          - BUG: non-primitive python objects can only be passed during
            .get_concrete_function() and must not be passed again when called.
            This is because non-primitive objects are interpreted as
            ``UnknownArgument`` by tensorflow.

        Parameters
        ----------
        meta : MetaIteration
            Namedtuple containing problem parameters.
        data : nested structure
            Sample data element for concrete function binding.
        states : UnrollState[]
            Initial problem parameter values and hidden state values for
            learned optimizer and teachers; created by UnrollStateManager.
        scale : tf.Tensor[]
            Random parameter scaling; applied multiplicatively.

        Returns
        -------
        tf.Graph
            Concrete function created with the specified problem inputs.
        """
        # time it
        start = time.time()

        if meta.validation:
            step = self.abstract_valid_step.get_concrete_function(
                data, states, scale, unroll=meta.unroll_len,
                problem=meta.problem, seed=meta.seed)
        else:
            # NOTE: weights are just placeholders
            step = self.abstract_train_step.get_concrete_function(
                data, states, scale,
                meta_loss_weight=tf.constant(0.5),
                imitation_loss_weight=tf.constant(0.5),
                unroll=meta.unroll_len, problem=meta.problem, seed=meta.seed)

        print("[{:.2f}s] Built concrete step: unroll={}, validation={}".format(
            time.time() - start, meta.unroll_len, meta.validation))

        return step
