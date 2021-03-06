import numpy as np

from spuq.utils.testing import *
from spuq.linalg.vector import *
from spuq.linalg.basis import *
from spuq.linalg.test_support import *


def test_vector_is_abstract():
    assert_raises(TypeError, Vector)


def test_flatvec_init():
    arr = np.array([1.0, 2, 3])
    FlatVector(arr)
    FlatVector([1.0, 2.0, 3.0])
    FlatVector([1, 2, 3])
    FlatVector([1, 2, 3], CanonicalBasis(3))
    assert_raises(TypeError, FlatVector, ["str", "str"])
    assert_raises(TypeError, FlatVector, [1, 2, 3], object)


def test_flatvec_as_array():
    fv1 = FlatVector([1, 2, 3])
    assert_equal(fv1.as_array(), np.array([1.0, 2, 3]))
    assert_is_instance(fv1.as_array()[0], float)


def test_flatvec_equals():
    fv1 = FlatVector([1, 2, 3])
    fv2 = FlatVector([1, 2, 3])
    fv3 = FlatVector([1, 2])
    fv4 = FlatVector([1, 2, 4])
    fv5 = FlatVector([1, 2, 3], FooBasis(3))

    # make sure both operators are overloaded
    assert_true(fv1 == fv2)
    assert_false(fv1 != fv2)
    assert_true(fv1 != fv3)
    assert_false(fv1 == fv3)

    # now test for (in)equality
    assert_equal(fv1, fv2)
    assert_not_equal(fv1, fv3)
    assert_not_equal(fv1, fv4)
    assert_not_equal(fv1, fv5)
    assert_equal(fv5, fv5)


def test_flatvec_copy():
    arr = np.array([1.0, 2, 3])
    fv1 = FlatVector(arr)
    fv2 = fv1.copy()
    assert_equal(fv1, fv2)
    fv1.coeffs[1] = 5
    assert_not_equal(fv1, fv2)


def test_flatvec_neg():
    fv1 = FlatVector([1.0, 2, 3])
    fv2 = FlatVector([-1.0, -2, -3])
    assert_equal(-fv1, fv2)
    assert_equal(fv1.coeffs[0], 1.0)


def test_flatvec_add():
    fv1 = FlatVector(np.array([1.0, 2, 3]))
    fv2 = FlatVector(np.array([7.0, 2, 5]))
    fv3 = FlatVector(np.array([8.0, 4, 8]))
    assert_equal(fv1 + fv2, fv3)
    fv1 += fv2
    assert_equal(fv1, fv3)

    fv4 = FlatVector([1, 2])
    fv5 = FlatVector([1, 2, 3], FooBasis(3))
    assert_raises(BasisMismatchError, lambda: fv1 + fv4)
    assert_raises(BasisMismatchError, lambda: fv1 + fv5)


def test_flatvec_sub():
    b = FooBasis(3)
    fv1 = FlatVector(np.array([5, 7, 10]), b)
    fv2 = FlatVector(np.array([2, 4, 6]), b)
    fv3 = FlatVector(np.array([3, 3, 4]), b)
    assert_equal(fv1 - fv2, fv3)

    isub = FlatVector.__isub__
    del FlatVector.__isub__
    assert_equal(fv1 - fv2, fv3)
    FlatVector.__isub__ = isub


def test_flatvec_mul():
    fv1 = FlatVector(np.array([1.0, 2, 3]))
    fv2 = FlatVector(np.array([2.5, 5, 7.5]))
    fv3 = FlatVector(np.array([2, 4, 6]))
    assert_equal(2.5 * fv1, fv2)
    assert_equal(2 * fv1, fv3)
    assert_equal(fv1 * 2.5, fv2)
    assert_equal(fv1 * 2, fv3)
    assert_raises(TypeError, lambda: fv1 * fv3)

    fv4 = FlatVector([1, 2, 3], FooBasis(3))
    fv5 = FlatVector([2, 4, 6], FooBasis(3))
    assert_equal(fv4 * 2, fv5)
    assert_equal(2 * fv4, fv5)


def test_flatvec_repr():
    fv1 = FlatVector(np.array([1.0, 2, 3]))
    assert_equal(str(fv1),
                 "<FlatVector basis=<CanonicalBasis dim=3>, " +
                 "coeffs=[ 1.  2.  3.]>")


test_main(True)
