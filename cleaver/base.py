from .compat import zip_longest, string_types
from .backend import CleaverBackend
from .identity import CleaverIdentityProvider
from cleaver import util


class Cleaver(object):

    def __init__(self, environ, identity, backend):
        """
        Create a new Cleaver instance.

        Not generally instantiated directly, but established automatically by
        ``cleaver.SplitMiddleware`` and used within a WSGI application via
        ``request.environ['cleaver']``.

        :param environ the WSGI environ dictionary for the current request
        :param identity any implementation of
                          ``identity.CleaverIdentityProvider`` or
                          a callable that emulates
                          ``identity.CleaverIdentityProvider.get_identity``.
        :param backend any implementation of
                          ``backend.CleaverBackend``
        """

        if not isinstance(identity, CleaverIdentityProvider) and \
            not callable(identity):
            raise RuntimeError(
                '%s must be callable or implement ' \
                    'cleaver.identity.CleaverIdentityProvider' % identity
            )
        if not isinstance(backend, CleaverBackend):
            raise RuntimeError(
                '%s must implement cleaver.backend.CleaverBackend' % backend
            )
        self._identity = identity
        self._backend = backend
        self._environ = environ

    @property
    def identity(self):
        """
        A unique identifier for the current visitor.
        """
        if hasattr(self._identity, 'get_identity'):
            return self._identity.get_identity(self._environ)
        return self._identity(self._environ)

    def split(self, experiment_name, *variants):
        """
        Used to split and track user experience amongst one or more variants.

        :param experiment_name a unique string name for the experiment
        :param *variants can take many forms, depending on usage.

            When no variants are provided, the test falls back to a simple
            True/False 50/50 split, e.g.,

            >>> sidebar() if split('include_sidebar') else empty()

            Otherwise, variants should be provided as arbitrary tuples in the
            format ('unique_string_label', any_value), ... e.g.,

            >>> split('text_color', ('red', '#F00'), ('blue', '#00F'))

            By default, variants are chosen with equal weight.  You can tip the
            scales if you like by passing a proportional *integer* weight as
            the third element in each variant tuple:

            >>> split('text_color', ('red', '#F00', 2), ('blue', '#00F', 4))
        """
        # Perform some minimal type checking
        if not isinstance(experiment_name, string_types):
            raise RuntimeError(
                'Invalid experiment name: %s must be a string.' % \
                    experiment_name
            )

        keys, values, weights = self._parse_variants(variants)
        b = self._backend

        # Record the experiment if it doesn't exist already
        experiment = b.get_experiment(experiment_name, keys)

        if experiment is None:
            b.save_experiment(experiment_name, keys)
            experiment = b.get_experiment(experiment_name, keys)
        else:
            if set(experiment.variants) != set(keys):
                raise RuntimeError(
                    'An experiment named %s already exists with different ' \
                        'variants.' % experiment_name
                )

        # Retrieve the variant assigned to the current user
        variant = b.get_variant(self.identity, experiment.name)
        if variant is None:
            # ...or choose (and store) one randomly if it doesn't exist yet...
            variant = next(util.random_variant(keys, weights))
            b.participate(self.identity, experiment.name, variant)

        return dict(zip(keys, values))[variant]

    def score(self, experiment_name):
        """
        Used to mark the current user's experiment variant as "converted" e.g.,

        "Suzy, who was shown the large button just signed up."

        :param experiment_name the string name of the experiment
        """
        self._backend.score(
            experiment_name,
            self._backend.get_variant(self.identity, experiment_name)
        )

    def _parse_variants(self, variants):
        if not len(variants):
            variants = [('True', True), ('False', False)]

        if len(variants) == 1:
            raise RuntimeError(
                'Experiments must have at least two variants ' \
                    '(a control and an alternative).'
            )

        def add_defaults(v):
            if len(v) < 3:
                v = tuple(
                    list(v) + (
                        [None, 1] if len(v) == 1 else [1]
                    )
                )

            # Perform some minimal type checking
            if not isinstance(v[0], string_types):
                raise RuntimeError(
                    'Invalid variant name: %s must be a string.' % \
                        v[0]
                )
            if not isinstance(v[2], int):
                raise RuntimeError(
                    'Invalid variant weight: %s must be an integer.' % \
                        v[2]
                )

            return v

        variants = map(
            add_defaults,
            variants
        )

        return zip_longest(*variants)
