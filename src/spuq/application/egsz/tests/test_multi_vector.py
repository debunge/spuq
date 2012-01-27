import numpy as np

from spuq.utils.testing import *
from spuq.application.egsz.multi_vector import MultiVector
from spuq.math_utils.multiindex import Multiindex
from spuq.math_utils.multiindex_set import MultiindexSet, createCompleteOrderSet
from spuq.linalg.vector import FlatVector

def test_init():
    mv = MultiVector()


def test_get_set():
    mv = MultiVector()
    mv[Multiindex([1, 2, 3])] = FlatVector([3, 4, 5])
    mv[Multiindex([0, 1, 2, 3])] = FlatVector([3, 4, 6])
    mv[Multiindex([1, 2, 3, 0])] = FlatVector([3, 4, 7])
    assert_equal(mv[Multiindex([1, 2, 3])], FlatVector([3, 4, 7]))
    assert_equal(mv[Multiindex([0, 1, 2, 3])], FlatVector([3, 4, 6]))

def test_keys():
    mv = MultiVector()
    mi1 = Multiindex([1, 2, 3])
    mi2 = Multiindex([1, 2, 4])
    mv[mi1] = FlatVector([3, 4, 5])
    mv[mi2] = FlatVector([3, 4, 7])
    keys = mv.keys()
    assert_equal(sorted(keys), sorted([mi1, mi2]))
    inds = mv.active_indices()
    assert_equal(sorted(inds), sorted([mi1, mi2]))

def test_copy():
    # make sure the vectors are copied and each have their own copy of
    # the data
    mv = MultiVector()
    mv[Multiindex([1, 2, 3])] = FlatVector([3, 4, 5])
    mv[Multiindex([1, 2, 4])] = FlatVector([3, 4, 7])
    assert_equal(mv[Multiindex([1, 2, 3])], FlatVector([3, 4, 5]))
    assert_equal(mv[Multiindex([1, 2, 4])], FlatVector([3, 4, 7]))
    mv2 = mv.copy()
    mv[Multiindex([1, 2, 3])].coeffs[2] = 8
    assert_equal(mv2[Multiindex([1, 2, 3])], FlatVector([3, 4, 5]))
    assert_equal(mv2[Multiindex([1, 2, 4])], FlatVector([3, 4, 7]))
    assert_equal(mv[Multiindex([1, 2, 3])], FlatVector([3, 4, 8]))


def test_set_defaults():
    mv = MultiVector()
    mis = createCompleteOrderSet(3, 4)
    mv.set_defaults(mis, FlatVector([3, 4, 5]))
    assert_equal(mv[Multiindex([1, 2, 1])], FlatVector([3, 4, 5]))
    assert_equal(mv[Multiindex()], FlatVector([3, 4, 5]))
    assert_raises(KeyError, mv.__getitem__, Multiindex([1, 2, 2]))


def test_equality():
    mv1 = MultiVector()
    mv2 = MultiVector()
    mv3 = MultiVector()
    mv4 = MultiVector()
    mis1 = createCompleteOrderSet(3, 4)
    mis2 = createCompleteOrderSet(3, 5)
    mv1.set_defaults(mis1, FlatVector([3, 4, 5]))
    mv2.set_defaults(mis1, FlatVector([3, 4, 5]))
    mv3.set_defaults(mis2, FlatVector([3, 4, 5]))
    mv4.set_defaults(mis1, FlatVector([3, 4, 6]))
    assert_true(mv1 == mv2)
    assert_false(mv1 != mv2)
    assert_true(mv1 != mv3)
    assert_false(mv1 == mv3)
    assert_true(mv1 != mv4)
    assert_false(mv1 == mv4)

def test_add():
    mv1 = MultiVector()
    mv2 = MultiVector()
    mv3 = MultiVector()
    mis1 = createCompleteOrderSet(3, 4)
    mv1.set_defaults(mis1, FlatVector([3, 4, 5]))
    mv2.set_defaults(mis1, FlatVector([6, 8, 12]))
    mv3.set_defaults(mis1, FlatVector([9, 12, 17]))
    assert_equal(mv1 + mv2, mv3)

def test_mul():
    mv1 = MultiVector()
    mv2 = MultiVector()
    mis1 = createCompleteOrderSet(3, 4)
    #mis2 = createCompleteOrderSet(3, 5)
    mv1.set_defaults(mis1, FlatVector([3, 4, 5]))
    mv2.set_defaults(mis1, FlatVector([6, 8, 10]))
    assert_equal(2 * mv1, mv2)
    assert_equal(mv1 * 2, mv2)
    assert_equal(2.0 * mv1, mv2)
    assert_equal(mv1 * 2.0, mv2)
    assert_equal(mv1[Multiindex()], FlatVector([3, 4, 5]))
    mv1 *= 2.0
    assert_equal(mv1, mv2)


def test_sub():
    pass

test_main()