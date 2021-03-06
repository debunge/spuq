import math
from abc import ABCMeta, abstractmethod, abstractproperty

import numpy as np

import spuq.polyquad._polynomials as _p
import spuq.utils.decorators as _dec


class PolynomialFamily(object):
    """Abstract base for families of (orthogonal) polynomials"""
    __metaclass__ = ABCMeta

    x = np.poly1d([1.0, 0.0])

    @abstractmethod
    def recurrence_coefficients(self, n):  # pragma: no cover
        return NotImplemented

    @abstractmethod
    def get_structure_coefficient(self, a, b, c):  # pragma: no cover
        """Return specific structure coefficient"""
        return NotImplemented

    def eval(self, n, x, all_degrees=False):
        """Evaluate polynomial of degree ``n`` at points ``x``"""
        values = _p.compute_poly(self.recurrence_coefficients, n, x)
        if all_degrees:
            return values
        else:
            return values[-1]

    def __getitem__(self, n):
        x = np.poly1d([1, 0])
        return self.eval(n, x)

    def get_coefficients(self, n):
        """Return coefficients of the polynomial with degree ``n`` of
        the family."""
        x = np.poly1d([1, 0])
        l = self.eval(n, x)
        return l.coeffs[::-1]

    def get_beta(self, n):
        """Return the coefficients beta needed to multiply a polynomial by x such that
        p.x * p[n] == beta[1] * p[n + 1] - beta[0] * p[n] + beta[-1] * p[n - 1]"""
        (a, b, c) = self.recurrence_coefficients(n)
        return (a / b, 1 / b, c / b)

    def get_structure_coefficients(self, n):
        """Return structure coefficients of indices up to ``n``"""

        structcoeffs = getattr(self, "_structcoeffs", np.empty((0, 0, 0)))

        if n > structcoeffs.shape[0]:
            structcoeffs = np.array(
                [[[self.get_structure_coefficient(a, b, c)
                   for a in xrange(n)]
                  for b in xrange(n)]
                 for c in xrange(n)])

        return structcoeffs[0:n, 0:n, 0:n]

    @abstractmethod
    def norm(self, n, sqrt=True):  # pragma: no cover
        """Return norm of the ``n``-th degree polynomial."""
        return NotImplemented

    @abstractproperty
    def normalised(self):  # pragma: no cover
        """True if polynomials are normalised."""
        return False


class BasePolynomialFamily(PolynomialFamily):
    """ """

    def __init__(self, rc_func, sqnorm_func=None, sc_func=None, normalised=False, cache_size=1000):
        if cache_size > 0:
            cache = _dec.simple_int_cache(cache_size)
        else:
            cache = lambda func: func

        self._rc_func = cache(rc_func)

        if sqnorm_func is None:
            sqnorm_func = lambda n: _p.sqnorm_from_rc(rc_func, n)
        self._sqnorm_func = cache(sqnorm_func)

        if sc_func is None:
            # needs to be implemented in _polynomials
            sc_func = NotImplemented
        self._sc_func = sc_func

        self._normalised = normalised

    def normalise(self):
        rc_func = _p.normalise_rc(self._rc_func, self._sqnorm_func)
        self._rc_func = rc_func
        self._sqnorm_func = None
        self._sc_func = NotImplemented
        self._normalised = True

    def recurrence_coefficients(self, n):
        return self._rc_func(n)

    def get_structure_coefficient(self, a, b, c):
        return self._sc_func(a, b, c)

    def norm(self, n, sqrt=True):
        """Return the norm of the `n`-th polynomial."""
        if self._normalised:
            return 1.0
        elif sqrt:
            return math.sqrt(self._sqnorm_func(n))
        else:
            return self._sqnorm_func(n)

    @property
    def normalised(self):
        """True if polynomials are normalised."""
        return self._normalised


class LegendrePolynomials(BasePolynomialFamily):

    def __init__(self, a= -1.0, b=1.0, normalised=True):
        rc_func = _p.rc_legendre
        sqnorm_func = _p.sqnorm_legendre
        if a != -1.0 or b != 1.0:
            rc_func = _p.rc_window_trans(rc_func, (-1, 1), (a, b))
            sqnorm_func = None

        super(self.__class__, self).__init__(rc_func, sqnorm_func)
        if normalised:
            self.normalise()


class StochasticHermitePolynomials(BasePolynomialFamily):

    def __init__(self, mu=0.0, sigma=1.0, normalised=True):
        rc_func = _p.rc_stoch_hermite
        sqnorm_func = _p.sqnorm_stoch_hermite
        if mu != 0.0 or sigma != 1.0:
            rc_func = _p.rc_shift_scale(rc_func, mu, sigma)
            sqnorm_func = None

        super(self.__class__, self).__init__(rc_func, sqnorm_func)
        if normalised:
            self.normalise()


class JacobiPolynomials(BasePolynomialFamily):

    def __init__(self, alpha, beta, a= -1.0, b=1.0, normalised=True):
        if alpha <= -1 or beta <= -1:
            raise TypeError("alpha and beta must be larger than -1")
        rc_func = lambda n: _p.rc_jacobi(n, alpha, beta)
        sqnorm_func = None
        if a != -1.0 or b != 1.0:
            rc_func = _p.rc_window_trans(rc_func, (-1.0, 1.0), (a, b))

        super(self.__class__, self).__init__(rc_func, sqnorm_func)
        if normalised:
            self.normalise()


class ChebyshevT(BasePolynomialFamily):

    def __init__(self, a= -1.0, b=1.0, normalised=True):
        rc_func = _p.rc_chebyshev_t
        sqnorm_func = None
        if a != -1.0 or b != 1.0:
            rc_func = _p.rc_window_trans(rc_func, (-1, 1), (a, b))

        super(self.__class__, self).__init__(rc_func, sqnorm_func)
        if normalised:
            self.normalise()


class ChebyshevU(BasePolynomialFamily):

    def __init__(self, a= -1.0, b=1.0, normalised=True):
        rc_func = _p.rc_chebyshev_u
        sqnorm_func = None
        if a != -1.0 or b != 1.0:
            rc_func = _p.rc_window_trans(rc_func, (-1, 1), (a, b))

        super(self.__class__, self).__init__(rc_func, sqnorm_func)
        if normalised:
            self.normalise()
