# Owner(s): ["module: tests"]

import operator
import random
import unittest
import warnings
from functools import reduce
from itertools import product

import numpy as np

import torch
from torch import tensor
from torch.testing import make_tensor
from torch.testing._internal.common_device_type import (
    dtypes,
    dtypesIfCPU,
    dtypesIfCUDA,
    get_all_device_types,
    instantiate_device_type_tests,
    onlyCPU,
    onlyCUDA,
    onlyNativeDeviceTypes,
    skipXLA,
)
from torch.testing._internal.common_dtype import (
    all_types_and,
    all_types_and_complex_and,
    all_types_complex_float8_and,
)
from torch.testing._internal.common_utils import (
    DeterministicGuard,
    noncontiguous_like,
    parametrize,
    run_tests,
    serialTest,
    skipIfMPS,
    skipIfTorchDynamo,
    TEST_CUDA,
    TestCase,
    xfailIfTorchDynamo,
)


class TestIndexing(TestCase):
    def test_index(self, device):
        def consec(size, start=1):
            sequence = torch.ones(torch.tensor(size).prod(0)).cumsum(0)
            sequence.add_(start - 1)
            return sequence.view(*size)

        reference = consec((3, 3, 3)).to(device)

        # empty tensor indexing
        self.assertEqual(
            reference[torch.LongTensor().to(device)], reference.new(0, 3, 3)
        )

        self.assertEqual(reference[0], consec((3, 3)), atol=0, rtol=0)
        self.assertEqual(reference[1], consec((3, 3), 10), atol=0, rtol=0)
        self.assertEqual(reference[2], consec((3, 3), 19), atol=0, rtol=0)
        self.assertEqual(reference[0, 1], consec((3,), 4), atol=0, rtol=0)
        self.assertEqual(reference[0:2], consec((2, 3, 3)), atol=0, rtol=0)
        self.assertEqual(reference[2, 2, 2], 27, atol=0, rtol=0)
        self.assertEqual(reference[:], consec((3, 3, 3)), atol=0, rtol=0)

        # indexing with Ellipsis
        self.assertEqual(
            reference[..., 2],
            torch.tensor([[3.0, 6.0, 9.0], [12.0, 15.0, 18.0], [21.0, 24.0, 27.0]]),
            atol=0,
            rtol=0,
        )
        self.assertEqual(
            reference[0, ..., 2], torch.tensor([3.0, 6.0, 9.0]), atol=0, rtol=0
        )
        self.assertEqual(reference[..., 2], reference[:, :, 2], atol=0, rtol=0)
        self.assertEqual(reference[0, ..., 2], reference[0, :, 2], atol=0, rtol=0)
        self.assertEqual(reference[0, 2, ...], reference[0, 2], atol=0, rtol=0)
        self.assertEqual(reference[..., 2, 2, 2], 27, atol=0, rtol=0)
        self.assertEqual(reference[2, ..., 2, 2], 27, atol=0, rtol=0)
        self.assertEqual(reference[2, 2, ..., 2], 27, atol=0, rtol=0)
        self.assertEqual(reference[2, 2, 2, ...], 27, atol=0, rtol=0)
        self.assertEqual(reference[...], reference, atol=0, rtol=0)

        reference_5d = consec((3, 3, 3, 3, 3)).to(device)
        self.assertEqual(
            reference_5d[..., 1, 0], reference_5d[:, :, :, 1, 0], atol=0, rtol=0
        )
        self.assertEqual(
            reference_5d[2, ..., 1, 0], reference_5d[2, :, :, 1, 0], atol=0, rtol=0
        )
        self.assertEqual(
            reference_5d[2, 1, 0, ..., 1], reference_5d[2, 1, 0, :, 1], atol=0, rtol=0
        )
        self.assertEqual(reference_5d[...], reference_5d, atol=0, rtol=0)

        # LongTensor indexing
        reference = consec((5, 5, 5)).to(device)
        idx = torch.LongTensor([2, 4]).to(device)
        self.assertEqual(reference[idx], torch.stack([reference[2], reference[4]]))
        # TODO: enable one indexing is implemented like in numpy
        # self.assertEqual(reference[2, idx], torch.stack([reference[2, 2], reference[2, 4]]))
        # self.assertEqual(reference[3, idx, 1], torch.stack([reference[3, 2], reference[3, 4]])[:, 1])

        # None indexing
        self.assertEqual(reference[2, None], reference[2].unsqueeze(0))
        self.assertEqual(
            reference[2, None, None], reference[2].unsqueeze(0).unsqueeze(0)
        )
        self.assertEqual(reference[2:4, None], reference[2:4].unsqueeze(1))
        self.assertEqual(
            reference[None, 2, None, None],
            reference.unsqueeze(0)[:, 2].unsqueeze(0).unsqueeze(0),
        )
        self.assertEqual(
            reference[None, 2:5, None, None],
            reference.unsqueeze(0)[:, 2:5].unsqueeze(2).unsqueeze(2),
        )

        # indexing 0-length slice
        self.assertEqual(torch.empty(0, 5, 5), reference[slice(0)])
        self.assertEqual(torch.empty(0, 5), reference[slice(0), 2])
        self.assertEqual(torch.empty(0, 5), reference[2, slice(0)])
        self.assertEqual(torch.tensor([]), reference[2, 1:1, 2])

        # indexing with step
        reference = consec((10, 10, 10)).to(device)
        self.assertEqual(reference[1:5:2], torch.stack([reference[1], reference[3]], 0))
        self.assertEqual(
            reference[1:6:2], torch.stack([reference[1], reference[3], reference[5]], 0)
        )
        self.assertEqual(reference[1:9:4], torch.stack([reference[1], reference[5]], 0))
        self.assertEqual(
            reference[2:4, 1:5:2],
            torch.stack([reference[2:4, 1], reference[2:4, 3]], 1),
        )
        self.assertEqual(
            reference[3, 1:6:2],
            torch.stack([reference[3, 1], reference[3, 3], reference[3, 5]], 0),
        )
        self.assertEqual(
            reference[None, 2, 1:9:4],
            torch.stack([reference[2, 1], reference[2, 5]], 0).unsqueeze(0),
        )
        self.assertEqual(
            reference[:, 2, 1:6:2],
            torch.stack(
                [reference[:, 2, 1], reference[:, 2, 3], reference[:, 2, 5]], 1
            ),
        )

        lst = [list(range(i, i + 10)) for i in range(0, 100, 10)]
        tensor = torch.DoubleTensor(lst).to(device)
        for _i in range(100):
            idx1_start = random.randrange(10)
            idx1_end = idx1_start + random.randrange(1, 10 - idx1_start + 1)
            idx1_step = random.randrange(1, 8)
            idx1 = slice(idx1_start, idx1_end, idx1_step)
            if random.randrange(2) == 0:
                idx2_start = random.randrange(10)
                idx2_end = idx2_start + random.randrange(1, 10 - idx2_start + 1)
                idx2_step = random.randrange(1, 8)
                idx2 = slice(idx2_start, idx2_end, idx2_step)
                lst_indexed = [l[idx2] for l in lst[idx1]]
                tensor_indexed = tensor[idx1, idx2]
            else:
                lst_indexed = lst[idx1]
                tensor_indexed = tensor[idx1]
            self.assertEqual(torch.DoubleTensor(lst_indexed), tensor_indexed)

        self.assertRaises(ValueError, lambda: reference[1:9:0])
        self.assertRaises(ValueError, lambda: reference[1:9:-1])

        self.assertRaises(IndexError, lambda: reference[1, 1, 1, 1])
        self.assertRaises(IndexError, lambda: reference[1, 1, 1, 1:1])
        self.assertRaises(IndexError, lambda: reference[3, 3, 3, 3, 3, 3, 3, 3])

        self.assertRaises(IndexError, lambda: reference[0.0])
        self.assertRaises(TypeError, lambda: reference[0.0:2.0])
        self.assertRaises(IndexError, lambda: reference[0.0, 0.0:2.0])
        self.assertRaises(IndexError, lambda: reference[0.0, :, 0.0:2.0])
        self.assertRaises(IndexError, lambda: reference[0.0, ..., 0.0:2.0])
        self.assertRaises(IndexError, lambda: reference[0.0, :, 0.0])

        def delitem():
            del reference[0]

        self.assertRaises(TypeError, delitem)

    @onlyNativeDeviceTypes
    @dtypes(torch.half, torch.double)
    def test_advancedindex(self, device, dtype):
        # Tests for Integer Array Indexing, Part I - Purely integer array
        # indexing

        def consec(size, start=1):
            # Creates the sequence in float since CPU half doesn't support the
            # needed operations. Converts to dtype before returning.
            numel = reduce(operator.mul, size, 1)
            sequence = torch.ones(numel, dtype=torch.float, device=device).cumsum(0)
            sequence.add_(start - 1)
            return sequence.view(*size).to(dtype=dtype)

        # pick a random valid indexer type
        def ri(indices):
            choice = random.randint(0, 2)
            if choice == 0:
                return torch.LongTensor(indices).to(device)
            elif choice == 1:
                return list(indices)
            else:
                return tuple(indices)

        def validate_indexing(x):
            self.assertEqual(x[[0]], consec((1,)))
            self.assertEqual(x[ri([0]),], consec((1,)))
            self.assertEqual(x[ri([3]),], consec((1,), 4))
            self.assertEqual(x[[2, 3, 4]], consec((3,), 3))
            self.assertEqual(x[ri([2, 3, 4]),], consec((3,), 3))
            self.assertEqual(
                x[ri([0, 2, 4]),], torch.tensor([1, 3, 5], dtype=dtype, device=device)
            )

        def validate_setting(x):
            x[[0]] = -2
            self.assertEqual(x[[0]], torch.tensor([-2], dtype=dtype, device=device))
            x[[0]] = -1
            self.assertEqual(
                x[ri([0]),], torch.tensor([-1], dtype=dtype, device=device)
            )
            x[[2, 3, 4]] = 4
            self.assertEqual(
                x[[2, 3, 4]], torch.tensor([4, 4, 4], dtype=dtype, device=device)
            )
            x[ri([2, 3, 4]),] = 3
            self.assertEqual(
                x[ri([2, 3, 4]),], torch.tensor([3, 3, 3], dtype=dtype, device=device)
            )
            x[ri([0, 2, 4]),] = torch.tensor([5, 4, 3], dtype=dtype, device=device)
            self.assertEqual(
                x[ri([0, 2, 4]),], torch.tensor([5, 4, 3], dtype=dtype, device=device)
            )

        # Only validates indexing and setting for halfs
        if dtype == torch.half:
            reference = consec((10,))
            validate_indexing(reference)
            validate_setting(reference)
            return

        # Case 1: Purely Integer Array Indexing
        reference = consec((10,))
        validate_indexing(reference)

        # setting values
        validate_setting(reference)

        # Tensor with stride != 1
        # strided is [1, 3, 5, 7]
        reference = consec((10,))
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(
            reference.storage(), storage_offset=0, size=torch.Size([4]), stride=[2]
        )

        self.assertEqual(strided[[0]], torch.tensor([1], dtype=dtype, device=device))
        self.assertEqual(
            strided[ri([0]),], torch.tensor([1], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([3]),], torch.tensor([7], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[[1, 2]], torch.tensor([3, 5], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([1, 2]),], torch.tensor([3, 5], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([[2, 1], [0, 3]]),],
            torch.tensor([[5, 3], [1, 7]], dtype=dtype, device=device),
        )

        # stride is [4, 8]
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(
            reference.storage(), storage_offset=4, size=torch.Size([2]), stride=[4]
        )
        self.assertEqual(strided[[0]], torch.tensor([5], dtype=dtype, device=device))
        self.assertEqual(
            strided[ri([0]),], torch.tensor([5], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([1]),], torch.tensor([9], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[[0, 1]], torch.tensor([5, 9], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([0, 1]),], torch.tensor([5, 9], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([[0, 1], [1, 0]]),],
            torch.tensor([[5, 9], [9, 5]], dtype=dtype, device=device),
        )

        # reference is 1 2
        #              3 4
        #              5 6
        reference = consec((3, 2))
        self.assertEqual(
            reference[ri([0, 1, 2]), ri([0])],
            torch.tensor([1, 3, 5], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[ri([0, 1, 2]), ri([1])],
            torch.tensor([2, 4, 6], dtype=dtype, device=device),
        )
        self.assertEqual(reference[ri([0]), ri([0])], consec((1,)))
        self.assertEqual(reference[ri([2]), ri([1])], consec((1,), 6))
        self.assertEqual(
            reference[[ri([0, 0]), ri([0, 1])]],
            torch.tensor([1, 2], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[[ri([0, 1, 1, 0, 2]), ri([1])]],
            torch.tensor([2, 4, 4, 2, 6], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[[ri([0, 0, 1, 1]), ri([0, 1, 0, 0])]],
            torch.tensor([1, 2, 3, 3], dtype=dtype, device=device),
        )

        rows = ri([[0, 0], [1, 2]])
        columns = ([0],)
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[1, 1], [3, 5]], dtype=dtype, device=device),
        )

        rows = ri([[0, 0], [1, 2]])
        columns = ri([1, 0])
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[2, 1], [4, 5]], dtype=dtype, device=device),
        )
        rows = ri([[0, 0], [1, 2]])
        columns = ri([[0, 1], [1, 0]])
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[1, 2], [4, 5]], dtype=dtype, device=device),
        )

        # setting values
        reference[ri([0]), ri([1])] = -1
        self.assertEqual(
            reference[ri([0]), ri([1])], torch.tensor([-1], dtype=dtype, device=device)
        )
        reference[ri([0, 1, 2]), ri([0])] = torch.tensor(
            [-1, 2, -4], dtype=dtype, device=device
        )
        self.assertEqual(
            reference[ri([0, 1, 2]), ri([0])],
            torch.tensor([-1, 2, -4], dtype=dtype, device=device),
        )
        reference[rows, columns] = torch.tensor(
            [[4, 6], [2, 3]], dtype=dtype, device=device
        )
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[4, 6], [2, 3]], dtype=dtype, device=device),
        )

        # Verify still works with Transposed (i.e. non-contiguous) Tensors

        reference = torch.tensor(
            [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]], dtype=dtype, device=device
        ).t_()

        # Transposed: [[0, 4, 8],
        #              [1, 5, 9],
        #              [2, 6, 10],
        #              [3, 7, 11]]

        self.assertEqual(
            reference[ri([0, 1, 2]), ri([0])],
            torch.tensor([0, 1, 2], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[ri([0, 1, 2]), ri([1])],
            torch.tensor([4, 5, 6], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[ri([0]), ri([0])], torch.tensor([0], dtype=dtype, device=device)
        )
        self.assertEqual(
            reference[ri([2]), ri([1])], torch.tensor([6], dtype=dtype, device=device)
        )
        self.assertEqual(
            reference[[ri([0, 0]), ri([0, 1])]],
            torch.tensor([0, 4], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[[ri([0, 1, 1, 0, 3]), ri([1])]],
            torch.tensor([4, 5, 5, 4, 7], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[[ri([0, 0, 1, 1]), ri([0, 1, 0, 0])]],
            torch.tensor([0, 4, 1, 1], dtype=dtype, device=device),
        )

        rows = ri([[0, 0], [1, 2]])
        columns = ([0],)
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[0, 0], [1, 2]], dtype=dtype, device=device),
        )

        rows = ri([[0, 0], [1, 2]])
        columns = ri([1, 0])
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[4, 0], [5, 2]], dtype=dtype, device=device),
        )
        rows = ri([[0, 0], [1, 3]])
        columns = ri([[0, 1], [1, 2]])
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[0, 4], [5, 11]], dtype=dtype, device=device),
        )

        # setting values
        reference[ri([0]), ri([1])] = -1
        self.assertEqual(
            reference[ri([0]), ri([1])], torch.tensor([-1], dtype=dtype, device=device)
        )
        reference[ri([0, 1, 2]), ri([0])] = torch.tensor(
            [-1, 2, -4], dtype=dtype, device=device
        )
        self.assertEqual(
            reference[ri([0, 1, 2]), ri([0])],
            torch.tensor([-1, 2, -4], dtype=dtype, device=device),
        )
        reference[rows, columns] = torch.tensor(
            [[4, 6], [2, 3]], dtype=dtype, device=device
        )
        self.assertEqual(
            reference[rows, columns],
            torch.tensor([[4, 6], [2, 3]], dtype=dtype, device=device),
        )

        # stride != 1

        # strided is [[1 3 5 7],
        #             [9 11 13 15]]

        reference = torch.arange(0.0, 24, dtype=dtype, device=device).view(3, 8)
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(reference.storage(), 1, size=torch.Size([2, 4]), stride=[8, 2])

        self.assertEqual(
            strided[ri([0, 1]), ri([0])],
            torch.tensor([1, 9], dtype=dtype, device=device),
        )
        self.assertEqual(
            strided[ri([0, 1]), ri([1])],
            torch.tensor([3, 11], dtype=dtype, device=device),
        )
        self.assertEqual(
            strided[ri([0]), ri([0])], torch.tensor([1], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[ri([1]), ri([3])], torch.tensor([15], dtype=dtype, device=device)
        )
        self.assertEqual(
            strided[[ri([0, 0]), ri([0, 3])]],
            torch.tensor([1, 7], dtype=dtype, device=device),
        )
        self.assertEqual(
            strided[[ri([1]), ri([0, 1, 1, 0, 3])]],
            torch.tensor([9, 11, 11, 9, 15], dtype=dtype, device=device),
        )
        self.assertEqual(
            strided[[ri([0, 0, 1, 1]), ri([0, 1, 0, 0])]],
            torch.tensor([1, 3, 9, 9], dtype=dtype, device=device),
        )

        rows = ri([[0, 0], [1, 1]])
        columns = ([0],)
        self.assertEqual(
            strided[rows, columns],
            torch.tensor([[1, 1], [9, 9]], dtype=dtype, device=device),
        )

        rows = ri([[0, 1], [1, 0]])
        columns = ri([1, 2])
        self.assertEqual(
            strided[rows, columns],
            torch.tensor([[3, 13], [11, 5]], dtype=dtype, device=device),
        )
        rows = ri([[0, 0], [1, 1]])
        columns = ri([[0, 1], [1, 2]])
        self.assertEqual(
            strided[rows, columns],
            torch.tensor([[1, 3], [11, 13]], dtype=dtype, device=device),
        )

        # setting values

        # strided is [[10, 11],
        #             [17, 18]]

        reference = torch.arange(0.0, 24, dtype=dtype, device=device).view(3, 8)
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(reference.storage(), 10, size=torch.Size([2, 2]), stride=[7, 1])
        self.assertEqual(
            strided[ri([0]), ri([1])], torch.tensor([11], dtype=dtype, device=device)
        )
        strided[ri([0]), ri([1])] = -1
        self.assertEqual(
            strided[ri([0]), ri([1])], torch.tensor([-1], dtype=dtype, device=device)
        )

        reference = torch.arange(0.0, 24, dtype=dtype, device=device).view(3, 8)
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(reference.storage(), 10, size=torch.Size([2, 2]), stride=[7, 1])
        self.assertEqual(
            strided[ri([0, 1]), ri([1, 0])],
            torch.tensor([11, 17], dtype=dtype, device=device),
        )
        strided[ri([0, 1]), ri([1, 0])] = torch.tensor(
            [-1, 2], dtype=dtype, device=device
        )
        self.assertEqual(
            strided[ri([0, 1]), ri([1, 0])],
            torch.tensor([-1, 2], dtype=dtype, device=device),
        )

        reference = torch.arange(0.0, 24, dtype=dtype, device=device).view(3, 8)
        strided = torch.tensor((), dtype=dtype, device=device)
        strided.set_(reference.storage(), 10, size=torch.Size([2, 2]), stride=[7, 1])

        rows = ri([[0], [1]])
        columns = ri([[0, 1], [0, 1]])
        self.assertEqual(
            strided[rows, columns],
            torch.tensor([[10, 11], [17, 18]], dtype=dtype, device=device),
        )
        strided[rows, columns] = torch.tensor(
            [[4, 6], [2, 3]], dtype=dtype, device=device
        )
        self.assertEqual(
            strided[rows, columns],
            torch.tensor([[4, 6], [2, 3]], dtype=dtype, device=device),
        )

        # Tests using less than the number of dims, and ellipsis

        # reference is 1 2
        #              3 4
        #              5 6
        reference = consec((3, 2))
        self.assertEqual(
            reference[ri([0, 2]),],
            torch.tensor([[1, 2], [5, 6]], dtype=dtype, device=device),
        )
        self.assertEqual(
            reference[ri([1]), ...], torch.tensor([[3, 4]], dtype=dtype, device=device)
        )
        self.assertEqual(
            reference[..., ri([1])],
            torch.tensor([[2], [4], [6]], dtype=dtype, device=device),
        )

        # verify too many indices fails
        with self.assertRaises(IndexError):
            reference[ri([1]), ri([0, 2]), ri([3])]

        # test invalid index fails
        reference = torch.empty(10, dtype=dtype, device=device)
        # can't test cuda because it is a device assert
        if not reference.is_cuda:
            for err_idx in (10, -11):
                with self.assertRaisesRegex(IndexError, r"out of"):
                    reference[err_idx]
                with self.assertRaisesRegex(IndexError, r"out of"):
                    reference[torch.LongTensor([err_idx]).to(device)]
                with self.assertRaisesRegex(IndexError, r"out of"):
                    reference[[err_idx]]

        def tensor_indices_to_np(tensor, indices):
            # convert the Torch Tensor to a numpy array
            tensor = tensor.to(device="cpu")
            npt = tensor.numpy()

            # convert indices
            idxs = tuple(
                i.tolist() if isinstance(i, torch.LongTensor) else i for i in indices
            )

            return npt, idxs

        def get_numpy(tensor, indices):
            npt, idxs = tensor_indices_to_np(tensor, indices)

            # index and return as a Torch Tensor
            return torch.tensor(npt[idxs], dtype=dtype, device=device)

        def set_numpy(tensor, indices, value):
            if not isinstance(value, int):
                if self.device_type != "cpu":
                    value = value.cpu()
                value = value.numpy()

            npt, idxs = tensor_indices_to_np(tensor, indices)
            npt[idxs] = value
            return npt

        def assert_get_eq(tensor, indexer):
            self.assertEqual(tensor[indexer], get_numpy(tensor, indexer))

        def assert_set_eq(tensor, indexer, val):
            pyt = tensor.clone()
            numt = tensor.clone()
            pyt[indexer] = val
            numt = torch.tensor(
                set_numpy(numt, indexer, val), dtype=dtype, device=device
            )
            self.assertEqual(pyt, numt)

        def assert_backward_eq(tensor, indexer):
            cpu = tensor.float().detach().clone().requires_grad_(True)
            outcpu = cpu[indexer]
            gOcpu = torch.rand_like(outcpu)
            outcpu.backward(gOcpu)
            dev = cpu.to(device).detach().requires_grad_(True)
            outdev = dev[indexer]
            outdev.backward(gOcpu.to(device))
            self.assertEqual(cpu.grad, dev.grad)

        def get_set_tensor(indexed, indexer):
            set_size = indexed[indexer].size()
            set_count = indexed[indexer].numel()
            set_tensor = torch.randperm(set_count).view(set_size).double().to(device)
            return set_tensor

        # Tensor is  0  1  2  3  4
        #            5  6  7  8  9
        #           10 11 12 13 14
        #           15 16 17 18 19
        reference = torch.arange(0.0, 20, dtype=dtype, device=device).view(4, 5)

        indices_to_test = [
            # grab the second, fourth columns
            [slice(None), [1, 3]],
            # first, third rows,
            [[0, 2], slice(None)],
            # weird shape
            [slice(None), [[0, 1], [2, 3]]],
            # negatives
            [[-1], [0]],
            [[0, 2], [-1]],
            [slice(None), [-1]],
        ]

        # only test dupes on gets
        get_indices_to_test = indices_to_test + [[slice(None), [0, 1, 1, 2, 2]]]

        for indexer in get_indices_to_test:
            assert_get_eq(reference, indexer)
            if self.device_type != "cpu":
                assert_backward_eq(reference, indexer)

        for indexer in indices_to_test:
            assert_set_eq(reference, indexer, 44)
            assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))

        reference = torch.arange(0.0, 160, dtype=dtype, device=device).view(4, 8, 5)

        indices_to_test = [
            [slice(None), slice(None), [0, 3, 4]],
            [slice(None), [2, 4, 5, 7], slice(None)],
            [[2, 3], slice(None), slice(None)],
            [slice(None), [0, 2, 3], [1, 3, 4]],
            [slice(None), [0], [1, 2, 4]],
            [slice(None), [0, 1, 3], [4]],
            [slice(None), [[0, 1], [1, 0]], [[2, 3]]],
            [slice(None), [[0, 1], [2, 3]], [[0]]],
            [slice(None), [[5, 6]], [[0, 3], [4, 4]]],
            [[0, 2, 3], [1, 3, 4], slice(None)],
            [[0], [1, 2, 4], slice(None)],
            [[0, 1, 3], [4], slice(None)],
            [[[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None)],
            [[[0, 1], [1, 0]], [[2, 3]], slice(None)],
            [[[0, 1], [2, 3]], [[0]], slice(None)],
            [[[2, 1]], [[0, 3], [4, 4]], slice(None)],
            [[[2]], [[0, 3], [4, 1]], slice(None)],
            # non-contiguous indexing subspace
            [[0, 2, 3], slice(None), [1, 3, 4]],
            # [...]
            # less dim, ellipsis
            [[0, 2]],
            [[0, 2], slice(None)],
            [[0, 2], Ellipsis],
            [[0, 2], slice(None), Ellipsis],
            [[0, 2], Ellipsis, slice(None)],
            [[0, 2], [1, 3]],
            [[0, 2], [1, 3], Ellipsis],
            [Ellipsis, [1, 3], [2, 3]],
            [Ellipsis, [2, 3, 4]],
            [Ellipsis, slice(None), [2, 3, 4]],
            [slice(None), Ellipsis, [2, 3, 4]],
            # ellipsis counts for nothing
            [Ellipsis, slice(None), slice(None), [0, 3, 4]],
            [slice(None), Ellipsis, slice(None), [0, 3, 4]],
            [slice(None), slice(None), Ellipsis, [0, 3, 4]],
            [slice(None), slice(None), [0, 3, 4], Ellipsis],
            [Ellipsis, [[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None)],
            [[[0, 1], [1, 0]], [[2, 1], [3, 5]], Ellipsis, slice(None)],
            [[[0, 1], [1, 0]], [[2, 1], [3, 5]], slice(None), Ellipsis],
        ]

        for indexer in indices_to_test:
            assert_get_eq(reference, indexer)
            assert_set_eq(reference, indexer, 212)
            assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))
            if torch.cuda.is_available():
                assert_backward_eq(reference, indexer)

        reference = torch.arange(0.0, 1296, dtype=dtype, device=device).view(3, 9, 8, 6)

        indices_to_test = [
            [slice(None), slice(None), slice(None), [0, 3, 4]],
            [slice(None), slice(None), [2, 4, 5, 7], slice(None)],
            [slice(None), [2, 3], slice(None), slice(None)],
            [[1, 2], slice(None), slice(None), slice(None)],
            [slice(None), slice(None), [0, 2, 3], [1, 3, 4]],
            [slice(None), slice(None), [0], [1, 2, 4]],
            [slice(None), slice(None), [0, 1, 3], [4]],
            [slice(None), slice(None), [[0, 1], [1, 0]], [[2, 3]]],
            [slice(None), slice(None), [[0, 1], [2, 3]], [[0]]],
            [slice(None), slice(None), [[5, 6]], [[0, 3], [4, 4]]],
            [slice(None), [0, 2, 3], [1, 3, 4], slice(None)],
            [slice(None), [0], [1, 2, 4], slice(None)],
            [slice(None), [0, 1, 3], [4], slice(None)],
            [slice(None), [[0, 1], [3, 4]], [[2, 3], [0, 1]], slice(None)],
            [slice(None), [[0, 1], [3, 4]], [[2, 3]], slice(None)],
            [slice(None), [[0, 1], [3, 2]], [[0]], slice(None)],
            [slice(None), [[2, 1]], [[0, 3], [6, 4]], slice(None)],
            [slice(None), [[2]], [[0, 3], [4, 2]], slice(None)],
            [[0, 1, 2], [1, 3, 4], slice(None), slice(None)],
            [[0], [1, 2, 4], slice(None), slice(None)],
            [[0, 1, 2], [4], slice(None), slice(None)],
            [[[0, 1], [0, 2]], [[2, 4], [1, 5]], slice(None), slice(None)],
            [[[0, 1], [1, 2]], [[2, 0]], slice(None), slice(None)],
            [[[2, 2]], [[0, 3], [4, 5]], slice(None), slice(None)],
            [[[2]], [[0, 3], [4, 5]], slice(None), slice(None)],
            [slice(None), [3, 4, 6], [0, 2, 3], [1, 3, 4]],
            [slice(None), [2, 3, 4], [1, 3, 4], [4]],
            [slice(None), [0, 1, 3], [4], [1, 3, 4]],
            [slice(None), [6], [0, 2, 3], [1, 3, 4]],
            [slice(None), [2, 3, 5], [3], [4]],
            [slice(None), [0], [4], [1, 3, 4]],
            [slice(None), [6], [0, 2, 3], [1]],
            [slice(None), [[0, 3], [3, 6]], [[0, 1], [1, 3]], [[5, 3], [1, 2]]],
            [[2, 2, 1], [0, 2, 3], [1, 3, 4], slice(None)],
            [[2, 0, 1], [1, 2, 3], [4], slice(None)],
            [[0, 1, 2], [4], [1, 3, 4], slice(None)],
            [[0], [0, 2, 3], [1, 3, 4], slice(None)],
            [[0, 2, 1], [3], [4], slice(None)],
            [[0], [4], [1, 3, 4], slice(None)],
            [[1], [0, 2, 3], [1], slice(None)],
            [[[1, 2], [1, 2]], [[0, 1], [2, 3]], [[2, 3], [3, 5]], slice(None)],
            # less dim, ellipsis
            [Ellipsis, [0, 3, 4]],
            [Ellipsis, slice(None), [0, 3, 4]],
            [Ellipsis, slice(None), slice(None), [0, 3, 4]],
            [slice(None), Ellipsis, [0, 3, 4]],
            [slice(None), slice(None), Ellipsis, [0, 3, 4]],
            [slice(None), [0, 2, 3], [1, 3, 4]],
            [slice(None), [0, 2, 3], [1, 3, 4], Ellipsis],
            [Ellipsis, [0, 2, 3], [1, 3, 4], slice(None)],
            [[0], [1, 2, 4]],
            [[0], [1, 2, 4], slice(None)],
            [[0], [1, 2, 4], Ellipsis],
            [[0], [1, 2, 4], Ellipsis, slice(None)],
            [[1]],
            [[0, 2, 1], [3], [4]],
            [[0, 2, 1], [3], [4], slice(None)],
            [[0, 2, 1], [3], [4], Ellipsis],
            [Ellipsis, [0, 2, 1], [3], [4]],
        ]

        for indexer in indices_to_test:
            assert_get_eq(reference, indexer)
            assert_set_eq(reference, indexer, 1333)
            assert_set_eq(reference, indexer, get_set_tensor(reference, indexer))
        indices_to_test += [
            [slice(None), slice(None), [[0, 1], [1, 0]], [[2, 3], [3, 0]]],
            [slice(None), slice(None), [[2]], [[0, 3], [4, 4]]],
        ]
        for indexer in indices_to_test:
            assert_get_eq(reference, indexer)
            assert_set_eq(reference, indexer, 1333)
            if self.device_type != "cpu":
                assert_backward_eq(reference, indexer)

    def test_advancedindex_big(self, device):
        reference = torch.arange(0, 123344, dtype=torch.int, device=device)

        self.assertEqual(
            reference[[0, 123, 44488, 68807, 123343],],
            torch.tensor([0, 123, 44488, 68807, 123343], dtype=torch.int),
        )

    def test_set_item_to_scalar_tensor(self, device):
        m = random.randint(1, 10)
        n = random.randint(1, 10)
        z = torch.randn([m, n], device=device)
        a = 1.0
        w = torch.tensor(a, requires_grad=True, device=device)
        z[:, 0] = w
        z.sum().backward()
        self.assertEqual(w.grad, m * a)

    def test_single_int(self, device):
        v = torch.randn(5, 7, 3, device=device)
        self.assertEqual(v[4].shape, (7, 3))

    def test_multiple_int(self, device):
        v = torch.randn(5, 7, 3, device=device)
        self.assertEqual(v[4].shape, (7, 3))
        self.assertEqual(v[4, :, 1].shape, (7,))

    def test_none(self, device):
        v = torch.randn(5, 7, 3, device=device)
        self.assertEqual(v[None].shape, (1, 5, 7, 3))
        self.assertEqual(v[:, None].shape, (5, 1, 7, 3))
        self.assertEqual(v[:, None, None].shape, (5, 1, 1, 7, 3))
        self.assertEqual(v[..., None].shape, (5, 7, 3, 1))

    def test_step(self, device):
        v = torch.arange(10, device=device)
        self.assertEqual(v[::1], v)
        self.assertEqual(v[::2].tolist(), [0, 2, 4, 6, 8])
        self.assertEqual(v[::3].tolist(), [0, 3, 6, 9])
        self.assertEqual(v[::11].tolist(), [0])
        self.assertEqual(v[1:6:2].tolist(), [1, 3, 5])

    def test_step_assignment(self, device):
        v = torch.zeros(4, 4, device=device)
        v[0, 1::2] = torch.tensor([3.0, 4.0], device=device)
        self.assertEqual(v[0].tolist(), [0, 3, 0, 4])
        self.assertEqual(v[1:].sum(), 0)

    def test_bool_indices(self, device):
        v = torch.randn(5, 7, 3, device=device)
        boolIndices = torch.tensor(
            [True, False, True, True, False], dtype=torch.bool, device=device
        )
        self.assertEqual(v[boolIndices].shape, (3, 7, 3))
        self.assertEqual(v[boolIndices], torch.stack([v[0], v[2], v[3]]))

        v = torch.tensor([True, False, True], dtype=torch.bool, device=device)
        boolIndices = torch.tensor(
            [True, False, False], dtype=torch.bool, device=device
        )
        uint8Indices = torch.tensor([1, 0, 0], dtype=torch.uint8, device=device)
        with warnings.catch_warnings(record=True) as w:
            v1 = v[boolIndices]
            v2 = v[uint8Indices]
            self.assertEqual(v1.shape, v2.shape)
            self.assertEqual(v1, v2)
            self.assertEqual(
                v[boolIndices], tensor([True], dtype=torch.bool, device=device)
            )
            self.assertEqual(len(w), 1)

    def test_bool_indices_accumulate(self, device):
        mask = torch.zeros(size=(10,), dtype=torch.bool, device=device)
        y = torch.ones(size=(10, 10), device=device)
        y.index_put_((mask,), y[mask], accumulate=True)
        self.assertEqual(y, torch.ones(size=(10, 10), device=device))

    def test_multiple_bool_indices(self, device):
        v = torch.randn(5, 7, 3, device=device)
        # note: these broadcast together and are transposed to the first dim
        mask1 = torch.tensor([1, 0, 1, 1, 0], dtype=torch.bool, device=device)
        mask2 = torch.tensor([1, 1, 1], dtype=torch.bool, device=device)
        self.assertEqual(v[mask1, :, mask2].shape, (3, 7))

    def test_byte_mask(self, device):
        v = torch.randn(5, 7, 3, device=device)
        mask = torch.ByteTensor([1, 0, 1, 1, 0]).to(device)
        with warnings.catch_warnings(record=True) as w:
            res = v[mask]
            self.assertEqual(res.shape, (3, 7, 3))
            self.assertEqual(res, torch.stack([v[0], v[2], v[3]]))
            self.assertEqual(len(w), 1)

        v = torch.tensor([1.0], device=device)
        self.assertEqual(v[v == 0], torch.tensor([], device=device))

    def test_byte_mask_accumulate(self, device):
        mask = torch.zeros(size=(10,), dtype=torch.uint8, device=device)
        y = torch.ones(size=(10, 10), device=device)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            y.index_put_((mask,), y[mask], accumulate=True)
            self.assertEqual(y, torch.ones(size=(10, 10), device=device))
            self.assertEqual(len(w), 2)

    @skipIfTorchDynamo(
        "This test causes SIGKILL when running with dynamo, https://github.com/pytorch/pytorch/issues/88472"
    )
    @serialTest(TEST_CUDA)
    def test_index_put_accumulate_large_tensor(self, device):
        # This test is for tensors with number of elements >= INT_MAX (2^31 - 1).
        N = (1 << 31) + 5
        dt = torch.int8
        a = torch.ones(N, dtype=dt, device=device)
        indices = torch.tensor(
            [-2, 0, -2, -1, 0, -1, 1], device=device, dtype=torch.long
        )
        values = torch.tensor([6, 5, 6, 6, 5, 7, 11], dtype=dt, device=device)

        a.index_put_((indices,), values, accumulate=True)

        self.assertEqual(a[0], 11)
        self.assertEqual(a[1], 12)
        self.assertEqual(a[2], 1)
        self.assertEqual(a[-3], 1)
        self.assertEqual(a[-2], 13)
        self.assertEqual(a[-1], 14)

        a = torch.ones((2, N), dtype=dt, device=device)
        indices0 = torch.tensor([0, -1, 0, 1], device=device, dtype=torch.long)
        indices1 = torch.tensor([-2, -1, 0, 1], device=device, dtype=torch.long)
        values = torch.tensor([12, 13, 10, 11], dtype=dt, device=device)

        a.index_put_((indices0, indices1), values, accumulate=True)

        self.assertEqual(a[0, 0], 11)
        self.assertEqual(a[0, 1], 1)
        self.assertEqual(a[1, 0], 1)
        self.assertEqual(a[1, 1], 12)
        self.assertEqual(a[:, 2], torch.ones(2, dtype=torch.int8))
        self.assertEqual(a[:, -3], torch.ones(2, dtype=torch.int8))
        self.assertEqual(a[0, -2], 13)
        self.assertEqual(a[1, -2], 1)
        self.assertEqual(a[-1, -1], 14)
        self.assertEqual(a[0, -1], 1)

    @onlyNativeDeviceTypes
    def test_index_put_accumulate_expanded_values(self, device):
        # checks the issue with cuda: https://github.com/pytorch/pytorch/issues/39227
        # and verifies consistency with CPU result
        t = torch.zeros((5, 2))
        t_dev = t.to(device)
        indices = [torch.tensor([0, 1, 2, 3]), torch.tensor([1])]
        indices_dev = [i.to(device) for i in indices]
        values0d = torch.tensor(1.0)
        values1d = torch.tensor([1.0])

        out_cuda = t_dev.index_put_(indices_dev, values0d.to(device), accumulate=True)
        out_cpu = t.index_put_(indices, values0d, accumulate=True)
        self.assertEqual(out_cuda.cpu(), out_cpu)

        out_cuda = t_dev.index_put_(indices_dev, values1d.to(device), accumulate=True)
        out_cpu = t.index_put_(indices, values1d, accumulate=True)
        self.assertEqual(out_cuda.cpu(), out_cpu)

        t = torch.zeros(4, 3, 2)
        t_dev = t.to(device)

        indices = [
            torch.tensor([0]),
            torch.arange(3)[:, None],
            torch.arange(2)[None, :],
        ]
        indices_dev = [i.to(device) for i in indices]
        values1d = torch.tensor([-1.0, -2.0])
        values2d = torch.tensor([[-1.0, -2.0]])

        out_cuda = t_dev.index_put_(indices_dev, values1d.to(device), accumulate=True)
        out_cpu = t.index_put_(indices, values1d, accumulate=True)
        self.assertEqual(out_cuda.cpu(), out_cpu)

        out_cuda = t_dev.index_put_(indices_dev, values2d.to(device), accumulate=True)
        out_cpu = t.index_put_(indices, values2d, accumulate=True)
        self.assertEqual(out_cuda.cpu(), out_cpu)

    @onlyCUDA
    def test_index_put_large_indices(self, device):
        def generate_indices(num_indices: int, index_range: int):
            indices = []
            for _ in range(num_indices):
                x = random.randint(0, index_range - 1)
                indices.append(x)
            return torch.tensor(indices)

        num_indices = 401988
        max_index_range = 2000
        target_index_range = [16, 256, 2000]
        for generated_index_range in target_index_range:
            # create CPU tensors
            a_tensor_size = (max_index_range, 256)
            a = torch.randn(a_tensor_size, dtype=torch.bfloat16)
            b = generate_indices(
                num_indices=num_indices, index_range=generated_index_range
            )
            c_tensor_size = (num_indices, 256)
            c = torch.randn(c_tensor_size, dtype=torch.bfloat16)
            # create GPU copies
            a_dev = a.to(device)
            b_dev = b.to(device)
            c_dev = c.to(device)
            # run
            a.index_put_(indices=[b], values=c, accumulate=True)
            a_dev.index_put_(indices=[b_dev], values=c_dev, accumulate=True)
            self.assertEqual(a_dev.cpu(), a)

    @onlyCUDA
    def test_index_put_accumulate_non_contiguous(self, device):
        t = torch.zeros((5, 2, 2))
        t_dev = t.to(device)
        t1 = t_dev[:, 0, :]
        t2 = t[:, 0, :]
        self.assertTrue(not t1.is_contiguous())
        self.assertTrue(not t2.is_contiguous())

        indices = [torch.tensor([0, 1])]
        indices_dev = [i.to(device) for i in indices]
        value = torch.randn(2, 2)
        out_cuda = t1.index_put_(indices_dev, value.to(device), accumulate=True)
        out_cpu = t2.index_put_(indices, value, accumulate=True)
        self.assertTrue(not t1.is_contiguous())
        self.assertTrue(not t2.is_contiguous())

        self.assertEqual(out_cuda.cpu(), out_cpu)

    @onlyCUDA
    @skipIfTorchDynamo("Not a suitable test for TorchDynamo")
    def test_index_put_accumulate_with_optional_tensors(self, device):
        # TODO: replace with a better solution.
        # Currently, here using torchscript to put None into indices.
        # on C++ it gives indices as a list of 2 optional tensors: first is null and
        # the second is a valid tensor.
        @torch.jit.script
        def func(x, i, v):
            idx = [None, i]
            x.index_put_(idx, v, accumulate=True)
            return x

        n = 4
        t = torch.arange(n * 2, dtype=torch.float32).reshape(n, 2)
        t_dev = t.to(device)
        indices = torch.tensor([1, 0])
        indices_dev = indices.to(device)
        value0d = torch.tensor(10.0)
        value1d = torch.tensor([1.0, 2.0])

        out_cuda = func(t_dev, indices_dev, value0d.cuda())
        out_cpu = func(t, indices, value0d)
        self.assertEqual(out_cuda.cpu(), out_cpu)

        out_cuda = func(t_dev, indices_dev, value1d.cuda())
        out_cpu = func(t, indices, value1d)
        self.assertEqual(out_cuda.cpu(), out_cpu)

    @onlyNativeDeviceTypes
    def test_index_put_accumulate_duplicate_indices(self, device):
        for i in range(1, 512):
            # generate indices by random walk, this will create indices with
            # lots of duplicates interleaved with each other
            delta = torch.empty(i, dtype=torch.double, device=device).uniform_(-1, 1)
            indices = delta.cumsum(0).long()

            input = torch.randn(indices.abs().max() + 1, device=device)
            values = torch.randn(indices.size(0), device=device)
            output = input.index_put((indices,), values, accumulate=True)

            input_list = input.tolist()
            indices_list = indices.tolist()
            values_list = values.tolist()
            for i, v in zip(indices_list, values_list):
                input_list[i] += v

            self.assertEqual(output, input_list)

    @onlyNativeDeviceTypes
    def test_index_ind_dtype(self, device):
        x = torch.randn(4, 4, device=device)
        ind_long = torch.randint(4, (4,), dtype=torch.long, device=device)
        ind_int = ind_long.int()
        src = torch.randn(4, device=device)
        ref = x[ind_long, ind_long]
        res = x[ind_int, ind_int]
        self.assertEqual(ref, res)
        ref = x[ind_long, :]
        res = x[ind_int, :]
        self.assertEqual(ref, res)
        ref = x[:, ind_long]
        res = x[:, ind_int]
        self.assertEqual(ref, res)
        # no repeating indices for index_put
        ind_long = torch.arange(4, dtype=torch.long, device=device)
        ind_int = ind_long.int()
        for accum in (True, False):
            inp_ref = x.clone()
            inp_res = x.clone()
            torch.index_put_(inp_ref, (ind_long, ind_long), src, accum)
            torch.index_put_(inp_res, (ind_int, ind_int), src, accum)
            self.assertEqual(inp_ref, inp_res)

    @skipXLA
    def test_index_put_accumulate_empty(self, device):
        # Regression test for https://github.com/pytorch/pytorch/issues/94667
        input = torch.rand([], dtype=torch.float32, device=device)
        with self.assertRaises(RuntimeError):
            input.index_put([], torch.tensor([1.0], device=device), True)

    def test_multiple_byte_mask(self, device):
        v = torch.randn(5, 7, 3, device=device)
        # note: these broadcast together and are transposed to the first dim
        mask1 = torch.ByteTensor([1, 0, 1, 1, 0]).to(device)
        mask2 = torch.ByteTensor([1, 1, 1]).to(device)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.assertEqual(v[mask1, :, mask2].shape, (3, 7))
            self.assertEqual(len(w), 2)

    def test_byte_mask2d(self, device):
        v = torch.randn(5, 7, 3, device=device)
        c = torch.randn(5, 7, device=device)
        num_ones = (c > 0).sum()
        r = v[c > 0]
        self.assertEqual(r.shape, (num_ones, 3))

    @skipIfTorchDynamo("Not a suitable test for TorchDynamo")
    def test_jit_indexing(self, device):
        def fn1(x):
            x[x < 50] = 1.0
            return x

        def fn2(x):
            x[0:50] = 1.0
            return x

        scripted_fn1 = torch.jit.script(fn1)
        scripted_fn2 = torch.jit.script(fn2)
        data = torch.arange(100, device=device, dtype=torch.float)
        out = scripted_fn1(data.detach().clone())
        ref = torch.tensor(
            np.concatenate((np.ones(50), np.arange(50, 100))),
            device=device,
            dtype=torch.float,
        )
        self.assertEqual(out, ref)
        out = scripted_fn2(data.detach().clone())
        self.assertEqual(out, ref)

    def test_int_indices(self, device):
        v = torch.randn(5, 7, 3, device=device)
        self.assertEqual(v[[0, 4, 2]].shape, (3, 7, 3))
        self.assertEqual(v[:, [0, 4, 2]].shape, (5, 3, 3))
        self.assertEqual(v[:, [[0, 1], [4, 3]]].shape, (5, 2, 2, 3))

    @dtypes(
        torch.cfloat, torch.cdouble, torch.float, torch.bfloat16, torch.long, torch.bool
    )
    @dtypesIfCPU(
        torch.cfloat, torch.cdouble, torch.float, torch.long, torch.bool, torch.bfloat16
    )
    @dtypesIfCUDA(
        torch.cfloat,
        torch.cdouble,
        torch.half,
        torch.long,
        torch.bool,
        torch.bfloat16,
        torch.float8_e5m2,
        torch.float8_e4m3fn,
    )
    def test_index_put_src_datatype(self, device, dtype):
        src = torch.ones(3, 2, 4, device=device, dtype=dtype)
        vals = torch.ones(3, 2, 4, device=device, dtype=dtype)
        indices = (torch.tensor([0, 2, 1]),)
        res = src.index_put_(indices, vals, accumulate=True)
        self.assertEqual(res.shape, src.shape)

    @dtypes(torch.float, torch.bfloat16, torch.long, torch.bool)
    @dtypesIfCPU(torch.float, torch.long, torch.bfloat16, torch.bool)
    @dtypesIfCUDA(torch.half, torch.long, torch.bfloat16, torch.bool)
    def test_index_src_datatype(self, device, dtype):
        src = torch.ones(3, 2, 4, device=device, dtype=dtype)
        # test index
        res = src[[0, 2, 1], :, :]
        self.assertEqual(res.shape, src.shape)
        # test index_put, no accum
        src[[0, 2, 1], :, :] = res
        self.assertEqual(res.shape, src.shape)

    def test_int_indices2d(self, device):
        # From the NumPy indexing example
        x = torch.arange(0, 12, device=device).view(4, 3)
        rows = torch.tensor([[0, 0], [3, 3]], device=device)
        columns = torch.tensor([[0, 2], [0, 2]], device=device)
        self.assertEqual(x[rows, columns].tolist(), [[0, 2], [9, 11]])

    def test_int_indices_broadcast(self, device):
        # From the NumPy indexing example
        x = torch.arange(0, 12, device=device).view(4, 3)
        rows = torch.tensor([0, 3], device=device)
        columns = torch.tensor([0, 2], device=device)
        result = x[rows[:, None], columns]
        self.assertEqual(result.tolist(), [[0, 2], [9, 11]])

    def test_empty_index(self, device):
        x = torch.arange(0, 12, device=device).view(4, 3)
        idx = torch.tensor([], dtype=torch.long, device=device)
        self.assertEqual(x[idx].numel(), 0)

        # empty assignment should have no effect but not throw an exception
        y = x.clone()
        y[idx] = -1
        self.assertEqual(x, y)

        mask = torch.zeros(4, 3, device=device).bool()
        y[mask] = -1
        self.assertEqual(x, y)

    def test_empty_ndim_index(self, device):
        x = torch.randn(5, device=device)
        self.assertEqual(
            torch.empty(0, 2, device=device),
            x[torch.empty(0, 2, dtype=torch.int64, device=device)],
        )

        x = torch.randn(2, 3, 4, 5, device=device)
        self.assertEqual(
            torch.empty(2, 0, 6, 4, 5, device=device),
            x[:, torch.empty(0, 6, dtype=torch.int64, device=device)],
        )

        x = torch.empty(10, 0, device=device)
        self.assertEqual(x[[1, 2]].shape, (2, 0))
        self.assertEqual(x[[], []].shape, (0,))
        with self.assertRaisesRegex(IndexError, "for dimension with size 0"):
            x[:, [0, 1]]

    def test_empty_ndim_index_bool(self, device):
        x = torch.randn(5, device=device)
        self.assertRaises(
            IndexError, lambda: x[torch.empty(0, 2, dtype=torch.uint8, device=device)]
        )

    def test_empty_slice(self, device):
        x = torch.randn(2, 3, 4, 5, device=device)
        y = x[:, :, :, 1]
        z = y[:, 1:1, :]
        self.assertEqual((2, 0, 4), z.shape)
        # this isn't technically necessary, but matches NumPy stride calculations.
        self.assertEqual((60, 20, 5), z.stride())
        self.assertTrue(z.is_contiguous())

    def test_index_getitem_copy_bools_slices(self, device):
        true = torch.tensor(1, dtype=torch.uint8, device=device)
        false = torch.tensor(0, dtype=torch.uint8, device=device)

        tensors = [torch.randn(2, 3, device=device), torch.tensor(3.0, device=device)]

        for a in tensors:
            self.assertNotEqual(a.data_ptr(), a[True].data_ptr())
            self.assertEqual(torch.empty(0, *a.shape), a[False])
            self.assertNotEqual(a.data_ptr(), a[true].data_ptr())
            self.assertEqual(torch.empty(0, *a.shape), a[false])
            self.assertEqual(a.data_ptr(), a[None].data_ptr())
            self.assertEqual(a.data_ptr(), a[...].data_ptr())

    def test_index_setitem_bools_slices(self, device):
        true = torch.tensor(1, dtype=torch.uint8, device=device)
        false = torch.tensor(0, dtype=torch.uint8, device=device)

        tensors = [torch.randn(2, 3, device=device), torch.tensor(3, device=device)]

        for a in tensors:
            # prefix with a 1,1, to ensure we are compatible with numpy which cuts off prefix 1s
            # (some of these ops already prefix a 1 to the size)
            neg_ones = torch.ones_like(a) * -1
            neg_ones_expanded = neg_ones.unsqueeze(0).unsqueeze(0)
            a[True] = neg_ones_expanded
            self.assertEqual(a, neg_ones)
            a[False] = 5
            self.assertEqual(a, neg_ones)
            a[true] = neg_ones_expanded * 2
            self.assertEqual(a, neg_ones * 2)
            a[false] = 5
            self.assertEqual(a, neg_ones * 2)
            a[None] = neg_ones_expanded * 3
            self.assertEqual(a, neg_ones * 3)
            a[...] = neg_ones_expanded * 4
            self.assertEqual(a, neg_ones * 4)
            if a.dim() == 0:
                with self.assertRaises(IndexError):
                    a[:] = neg_ones_expanded * 5

    def test_index_scalar_with_bool_mask(self, device):
        a = torch.tensor(1, device=device)
        uintMask = torch.tensor(True, dtype=torch.uint8, device=device)
        boolMask = torch.tensor(True, dtype=torch.bool, device=device)
        self.assertEqual(a[uintMask], a[boolMask])
        self.assertEqual(a[uintMask].dtype, a[boolMask].dtype)

        a = torch.tensor(True, dtype=torch.bool, device=device)
        self.assertEqual(a[uintMask], a[boolMask])
        self.assertEqual(a[uintMask].dtype, a[boolMask].dtype)

    def test_setitem_expansion_error(self, device):
        true = torch.tensor(True, device=device)
        a = torch.randn(2, 3, device=device)
        # check prefix with  non-1s doesn't work
        a_expanded = a.expand(torch.Size([5, 1]) + a.size())
        # NumPy: ValueError
        with self.assertRaises(RuntimeError):
            a[True] = a_expanded
        with self.assertRaises(RuntimeError):
            a[true] = a_expanded

    def test_getitem_scalars(self, device):
        zero = torch.tensor(0, dtype=torch.int64, device=device)
        one = torch.tensor(1, dtype=torch.int64, device=device)

        # non-scalar indexed with scalars
        a = torch.randn(2, 3, device=device)
        self.assertEqual(a[0], a[zero])
        self.assertEqual(a[0][1], a[zero][one])
        self.assertEqual(a[0, 1], a[zero, one])
        self.assertEqual(a[0, one], a[zero, 1])

        # indexing by a scalar should slice (not copy)
        self.assertEqual(a[0, 1].data_ptr(), a[zero, one].data_ptr())
        self.assertEqual(a[1].data_ptr(), a[one.int()].data_ptr())
        self.assertEqual(a[1].data_ptr(), a[one.short()].data_ptr())

        # scalar indexed with scalar
        r = torch.randn((), device=device)
        with self.assertRaises(IndexError):
            r[:]
        with self.assertRaises(IndexError):
            r[zero]
        self.assertEqual(r, r[...])

    def test_setitem_scalars(self, device):
        zero = torch.tensor(0, dtype=torch.int64)

        # non-scalar indexed with scalars
        a = torch.randn(2, 3, device=device)
        a_set_with_number = a.clone()
        a_set_with_scalar = a.clone()
        b = torch.randn(3, device=device)

        a_set_with_number[0] = b
        a_set_with_scalar[zero] = b
        self.assertEqual(a_set_with_number, a_set_with_scalar)
        a[1, zero] = 7.7
        self.assertEqual(7.7, a[1, 0])

        # scalar indexed with scalars
        r = torch.randn((), device=device)
        with self.assertRaises(IndexError):
            r[:] = 8.8
        with self.assertRaises(IndexError):
            r[zero] = 8.8
        r[...] = 9.9
        self.assertEqual(9.9, r)

    def test_basic_advanced_combined(self, device):
        # From the NumPy indexing example
        x = torch.arange(0, 12, device=device).view(4, 3)
        self.assertEqual(x[1:2, 1:3], x[1:2, [1, 2]])
        self.assertEqual(x[1:2, 1:3].tolist(), [[4, 5]])

        # Check that it is a copy
        unmodified = x.clone()
        x[1:2, [1, 2]].zero_()
        self.assertEqual(x, unmodified)

        # But assignment should modify the original
        unmodified = x.clone()
        x[1:2, [1, 2]] = 0
        self.assertNotEqual(x, unmodified)

    def test_int_assignment(self, device):
        x = torch.arange(0, 4, device=device).view(2, 2)
        x[1] = 5
        self.assertEqual(x.tolist(), [[0, 1], [5, 5]])

        x = torch.arange(0, 4, device=device).view(2, 2)
        x[1] = torch.arange(5, 7, device=device)
        self.assertEqual(x.tolist(), [[0, 1], [5, 6]])

    def test_byte_tensor_assignment(self, device):
        x = torch.arange(0.0, 16, device=device).view(4, 4)
        b = torch.ByteTensor([True, False, True, False]).to(device)
        value = torch.tensor([3.0, 4.0, 5.0, 6.0], device=device)

        with warnings.catch_warnings(record=True) as w:
            x[b] = value
            self.assertEqual(len(w), 1)

        self.assertEqual(x[0], value)
        self.assertEqual(x[1], torch.arange(4.0, 8, device=device))
        self.assertEqual(x[2], value)
        self.assertEqual(x[3], torch.arange(12.0, 16, device=device))

    def test_variable_slicing(self, device):
        x = torch.arange(0, 16, device=device).view(4, 4)
        indices = torch.IntTensor([0, 1]).to(device)
        i, j = indices
        self.assertEqual(x[i:j], x[0:1])

    def test_ellipsis_tensor(self, device):
        x = torch.arange(0, 9, device=device).view(3, 3)
        idx = torch.tensor([0, 2], device=device)
        self.assertEqual(x[..., idx].tolist(), [[0, 2], [3, 5], [6, 8]])
        self.assertEqual(x[idx, ...].tolist(), [[0, 1, 2], [6, 7, 8]])

    def test_unravel_index_errors(self, device):
        with self.assertRaisesRegex(TypeError, r"expected 'indices' to be integer"):
            torch.unravel_index(torch.tensor(0.5, device=device), (2, 2))

        with self.assertRaisesRegex(TypeError, r"expected 'indices' to be integer"):
            torch.unravel_index(torch.tensor([], device=device), (10, 3, 5))

        with self.assertRaisesRegex(
            TypeError, r"expected 'shape' to be int or sequence"
        ):
            torch.unravel_index(
                torch.tensor([1], device=device, dtype=torch.int64),
                torch.tensor([1, 2, 3]),
            )

        with self.assertRaisesRegex(
            TypeError, r"expected 'shape' sequence to only contain ints"
        ):
            torch.unravel_index(
                torch.tensor([1], device=device, dtype=torch.int64), (1, 2, 2.0)
            )

        with self.assertRaisesRegex(
            ValueError, r"'shape' cannot have negative values, but got \(2, -3\)"
        ):
            torch.unravel_index(torch.tensor(0, device=device), (2, -3))

    def test_invalid_index(self, device):
        x = torch.arange(0, 16, device=device).view(4, 4)
        self.assertRaisesRegex(TypeError, "slice indices", lambda: x["0":"1"])

    def test_out_of_bound_index(self, device):
        x = torch.arange(0, 100, device=device).view(2, 5, 10)
        self.assertRaisesRegex(
            IndexError,
            "index 5 is out of bounds for dimension 1 with size 5",
            lambda: x[0, 5],
        )
        self.assertRaisesRegex(
            IndexError,
            "index 4 is out of bounds for dimension 0 with size 2",
            lambda: x[4, 5],
        )
        self.assertRaisesRegex(
            IndexError,
            "index 15 is out of bounds for dimension 2 with size 10",
            lambda: x[0, 1, 15],
        )
        self.assertRaisesRegex(
            IndexError,
            "index 12 is out of bounds for dimension 2 with size 10",
            lambda: x[:, :, 12],
        )

    def test_zero_dim_index(self, device):
        x = torch.tensor(10, device=device)
        self.assertEqual(x, x.item())

        def runner():
            print(x[0])
            return x[0]

        self.assertRaisesRegex(IndexError, "invalid index", runner)

    @onlyCUDA
    def test_invalid_device(self, device):
        idx = torch.tensor([0, 1])
        b = torch.zeros(5, device=device)
        c = torch.tensor([1.0, 2.0], device="cpu")

        for accumulate in [True, False]:
            self.assertRaises(
                RuntimeError,
                lambda: torch.index_put_(b, (idx,), c, accumulate=accumulate),
            )

    @onlyCUDA
    def test_cpu_indices(self, device):
        idx = torch.tensor([0, 1])
        b = torch.zeros(2, device=device)
        x = torch.ones(10, device=device)
        x[idx] = b  # index_put_
        ref = torch.ones(10, device=device)
        ref[:2] = 0
        self.assertEqual(x, ref, atol=0, rtol=0)
        out = x[idx]  # index
        self.assertEqual(out, torch.zeros(2, device=device), atol=0, rtol=0)

    @dtypes(torch.long, torch.float32)
    def test_take_along_dim(self, device, dtype):
        def _test_against_numpy(t, indices, dim):
            actual = torch.take_along_dim(t, indices, dim=dim)
            t_np = t.cpu().numpy()
            indices_np = indices.cpu().numpy()
            expected = np.take_along_axis(t_np, indices_np, axis=dim)
            self.assertEqual(actual, expected, atol=0, rtol=0)

        for shape in [(3, 2), (2, 3, 5), (2, 4, 0), (2, 3, 1, 4)]:
            for noncontiguous in [True, False]:
                t = make_tensor(
                    shape, device=device, dtype=dtype, noncontiguous=noncontiguous
                )
                for dim in list(range(t.ndim)) + [None]:
                    if dim is None:
                        indices = torch.argsort(t.view(-1))
                    else:
                        indices = torch.argsort(t, dim=dim)

                _test_against_numpy(t, indices, dim)

        # test broadcasting
        t = torch.ones((3, 4, 1), device=device)
        indices = torch.ones((1, 2, 5), dtype=torch.long, device=device)

        _test_against_numpy(t, indices, 1)

        # test empty indices
        t = torch.ones((3, 4, 5), device=device)
        indices = torch.ones((3, 0, 5), dtype=torch.long, device=device)

        _test_against_numpy(t, indices, 1)

    @dtypes(torch.long, torch.float)
    def test_take_along_dim_invalid(self, device, dtype):
        shape = (2, 3, 1, 4)
        dim = 0
        t = make_tensor(shape, device=device, dtype=dtype)
        indices = torch.argsort(t, dim=dim)

        # dim of `t` and `indices` does not match
        with self.assertRaisesRegex(
            RuntimeError, "input and indices should have the same number of dimensions"
        ):
            torch.take_along_dim(t, indices[0], dim=0)

        # invalid `indices` dtype
        with self.assertRaisesRegex(RuntimeError, r"dtype of indices should be Long"):
            torch.take_along_dim(t, indices.to(torch.bool), dim=0)

        with self.assertRaisesRegex(RuntimeError, r"dtype of indices should be Long"):
            torch.take_along_dim(t, indices.to(torch.float), dim=0)

        with self.assertRaisesRegex(RuntimeError, r"dtype of indices should be Long"):
            torch.take_along_dim(t, indices.to(torch.int32), dim=0)

        # invalid axis
        with self.assertRaisesRegex(IndexError, "Dimension out of range"):
            torch.take_along_dim(t, indices, dim=-7)

        with self.assertRaisesRegex(IndexError, "Dimension out of range"):
            torch.take_along_dim(t, indices, dim=7)

    @onlyCUDA
    @dtypes(torch.float)
    def test_gather_take_along_dim_cross_device(self, device, dtype):
        shape = (2, 3, 1, 4)
        dim = 0
        t = make_tensor(shape, device=device, dtype=dtype)
        indices = torch.argsort(t, dim=dim)

        with self.assertRaisesRegex(
            RuntimeError, "Expected all tensors to be on the same device"
        ):
            torch.gather(t, 0, indices.cpu())

        with self.assertRaisesRegex(
            RuntimeError,
            r"Expected tensor to have .* but got tensor with .* torch.take_along_dim()",
        ):
            torch.take_along_dim(t, indices.cpu(), dim=0)

        with self.assertRaisesRegex(
            RuntimeError, "Expected all tensors to be on the same device"
        ):
            torch.gather(t.cpu(), 0, indices)

        with self.assertRaisesRegex(
            RuntimeError,
            r"Expected tensor to have .* but got tensor with .* torch.take_along_dim()",
        ):
            torch.take_along_dim(t.cpu(), indices, dim=0)

    @onlyCUDA
    def test_cuda_broadcast_index_use_deterministic_algorithms(self, device):
        with DeterministicGuard(True):
            idx1 = torch.tensor([0])
            idx2 = torch.tensor([2, 6])
            idx3 = torch.tensor([1, 5, 7])

            tensor_a = torch.rand(13, 11, 12, 13, 12).cpu()
            tensor_b = tensor_a.to(device=device)
            tensor_a[idx1] = 1.0
            tensor_a[idx1, :, idx2, idx2, :] = 2.0
            tensor_a[:, idx1, idx3, :, idx3] = 3.0
            tensor_b[idx1] = 1.0
            tensor_b[idx1, :, idx2, idx2, :] = 2.0
            tensor_b[:, idx1, idx3, :, idx3] = 3.0
            self.assertEqual(tensor_a, tensor_b.cpu(), atol=0, rtol=0)

            tensor_a = torch.rand(10, 11).cpu()
            tensor_b = tensor_a.to(device=device)
            tensor_a[idx3] = 1.0
            tensor_a[idx2, :] = 2.0
            tensor_a[:, idx2] = 3.0
            tensor_a[:, idx1] = 4.0
            tensor_b[idx3] = 1.0
            tensor_b[idx2, :] = 2.0
            tensor_b[:, idx2] = 3.0
            tensor_b[:, idx1] = 4.0
            self.assertEqual(tensor_a, tensor_b.cpu(), atol=0, rtol=0)

            tensor_a = torch.rand(10, 10).cpu()
            tensor_b = tensor_a.to(device=device)
            tensor_a[[8]] = 1.0
            tensor_b[[8]] = 1.0
            self.assertEqual(tensor_a, tensor_b.cpu(), atol=0, rtol=0)

            tensor_a = torch.rand(10).cpu()
            tensor_b = tensor_a.to(device=device)
            tensor_a[6] = 1.0
            tensor_b[6] = 1.0
            self.assertEqual(tensor_a, tensor_b.cpu(), atol=0, rtol=0)

    def test_index_limits(self, device):
        #  Regression test for https://github.com/pytorch/pytorch/issues/115415
        t = torch.tensor([], device=device)
        idx_min = torch.iinfo(torch.int64).min
        idx_max = torch.iinfo(torch.int64).max
        self.assertRaises(IndexError, lambda: t[idx_min])
        self.assertRaises(IndexError, lambda: t[idx_max])

    @dtypes(*all_types_and_complex_and(torch.half, torch.bool, torch.bfloat16))
    def test_index_copy(self, device, dtype):
        # We just test for num_copy <= num_dest, as otherwise there are repeated indices
        # and the behavior is undefined
        num_copy, num_dest = 3, 5

        def make_arg(batch_sizes, n, dim, contig):
            size_arg = batch_sizes[:dim] + (n,) + batch_sizes[dim:]
            return make_tensor(
                size_arg,
                dtype=dtype,
                device=device,
                low=None,
                high=None,
                noncontiguous=not contig,
            )

        def ref_index_copy(tgt, dim, idx, src):
            for i in range(idx.size(0)):
                idx_dest = dim * (slice(None),) + (idx[i],)
                idx_src = dim * (slice(None),) + (i,)
                tgt[idx_dest] = src[idx_src]

        # More thorough testing as in index_add
        for dest_contig, src_contig, index_contig in product([True, False], repeat=3):
            for other_sizes in ((), (4, 5)):
                for dim in range(len(other_sizes)):
                    dest = make_arg(other_sizes, num_dest, dim, dest_contig)
                    src = make_arg(other_sizes, num_copy, dim, src_contig)
                    idx = torch.randperm(num_dest, dtype=torch.int64, device=device)[
                        :num_copy
                    ]
                    if not index_contig:
                        idx = torch.repeat_interleave(idx, 2, dim=-1)
                        idx = idx[..., ::2]
                    dest2 = dest.clone()
                    dest.index_copy_(dim, idx, src)
                    ref_index_copy(dest2, dim, idx, src)
                    self.assertEqual(dest, dest2)

    @parametrize("reduce", ["prod", "amin", "amax", "mean"])
    @dtypes(*all_types_and(torch.half, torch.bfloat16))
    def test_index_reduce(self, device, dtype, reduce):
        size = (3, 4, 5)
        index_dtypes = [torch.int, torch.long]
        include_selfs = [True, False]
        amin_init = float("inf") if dtype.is_floating_point else torch.iinfo(dtype).max
        amax_init = -float("inf") if dtype.is_floating_point else torch.iinfo(dtype).min
        reduction_init = {"prod": 1, "mean": 0, "amin": amin_init, "amax": amax_init}

        for dest_noncontig, src_noncontig, index_noncontig in product(
            [True, False], repeat=3
        ):
            for idx_dtype, include_self in product(index_dtypes, include_selfs):
                for dim in range(len(size)):
                    num_src = np.random.randint(10)
                    num_dest = size[dim]
                    dest = make_tensor(
                        size, device=device, dtype=dtype, noncontiguous=dest_noncontig
                    )
                    src_size = size[:dim] + (num_src,) + size[dim + 1 :]
                    src = make_tensor(
                        src_size,
                        device=device,
                        dtype=dtype,
                        noncontiguous=src_noncontig,
                    )
                    idx = torch.testing.make_tensor(
                        num_src,
                        low=0,
                        high=num_dest,
                        dtype=idx_dtype,
                        device=device,
                        noncontiguous=index_noncontig,
                    )
                    expected = dest.clone()
                    dest.index_reduce_(dim, idx, src, reduce, include_self=include_self)
                    # fill rows in idx with reduction inits if include_self=False
                    if not include_self:
                        expected.index_fill_(dim, idx.long(), reduction_init[reduce])
                    expected = expected.transpose(0, dim)
                    src = src.transpose(0, dim)
                    for i in range(num_src):
                        if reduce == "prod":
                            expected[idx[i]] *= src[i]
                        elif reduce == "amin":
                            torch.minimum(
                                expected[idx[i]], src[i], out=expected[idx[i]]
                            )
                        elif reduce == "amax":
                            torch.maximum(
                                expected[idx[i]], src[i], out=expected[idx[i]]
                            )
                        else:
                            expected[idx[i]] += src[i]
                    if reduce == "mean":
                        counts = (
                            torch.ones_like(expected)
                            if include_self
                            else torch.zeros_like(expected)
                        )
                        counts.index_add_(0, idx, torch.ones_like(src))
                        counts.masked_fill_(counts == 0, 1)
                        if dtype.is_floating_point:
                            expected.div_(counts)
                        else:
                            expected.div_(counts, rounding_mode="floor")
                    expected = expected.transpose(0, dim)

                    self.assertEqual(dest, expected)

    @onlyCUDA
    def test_index_add_bfloat16(self, device):
        inp_tensor = torch.randn(5, 3, device="cpu").bfloat16()
        t = torch.tensor(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=torch.bfloat16, device="cpu"
        )
        index = torch.tensor([0, 4, 2], device="cpu")
        out_cpu = inp_tensor.index_add(0, index, t)

        inp_tensor = inp_tensor.to(device=device)
        t = t.to(device=device)
        index = index.to(device=device)
        out_gpu = inp_tensor.index_add(0, index, t)

        self.assertEqual(out_cpu, out_gpu, atol=1e-2, rtol=0)

    def test_index_add(self):
        for device in get_all_device_types():
            for dest_contig, src_contig, index_contig in product(
                [True, False], repeat=3
            ):
                for other_sizes in ((), (4, 5)):
                    for dtype in [torch.int, torch.long]:
                        num_copy, num_dest = 3, 3
                        dest = torch.randn(num_dest, *other_sizes, device=device)
                        if not dest_contig:
                            dest = make_tensor(
                                dest.shape,
                                device=device,
                                dtype=dest.dtype,
                                noncontiguous=True,
                            )
                        src = torch.randn(num_copy, *other_sizes, device=device)
                        if not src_contig:
                            src = noncontiguous_like(src)
                        idx = torch.randperm(
                            num_dest, dtype=dtype, device=device
                        ).narrow(0, 0, num_copy)
                        if not index_contig:
                            idx = noncontiguous_like(idx)
                        # index_add_ without alpha argument
                        dest2 = dest.clone()
                        dest.index_add_(0, idx, src)
                        for i in range(idx.size(0)):
                            dest2[idx[i]] += src[i]
                        self.assertEqual(dest, dest2)
                        # index_add_ with alpha argument
                        dest2 = dest.clone()
                        dest.index_add_(0, idx, src, alpha=2)
                        for i in range(idx.size(0)):
                            dest2[idx[i]] += src[i] * 2
                        self.assertEqual(dest, dest2)

    # onlyNativeDeviceTypes due to an XLA error:
    # https://github.com/pytorch/pytorch/issues/53256
    @onlyNativeDeviceTypes
    @dtypes(*all_types_and_complex_and(torch.half, torch.bool, torch.bfloat16))
    def test_index_copy_scalars(self, device, dtype):
        # Create the 8 possible combinations of scalar sizes for target / index / source
        scalars = (
            (
                make_tensor(size_t, dtype=dtype, device=device, low=None, high=None),
                make_tensor(size_i, dtype=torch.int64, device=device, low=0, high=1),
                make_tensor(size_s, dtype=dtype, device=device, low=None, high=None),
            )
            for size_t, size_i, size_s in product([(), (1,)], repeat=3)
        )
        for target, idx, source in scalars:
            target.index_copy_(0, idx, source)
            self.assertEqual(target.item(), source.item())

    @onlyCPU
    def test_errors_index_copy(self, device):
        # We do not test the GPU as the CUDA_ASSERT would break the CUDA context
        idx_dim = 8
        tgt_dim = 5
        batch_dim = 3

        # Too large of an index
        a = torch.randn(batch_dim, tgt_dim, device=device)
        idx = torch.full((idx_dim,), tgt_dim, device=device)
        c = torch.zeros(batch_dim, idx_dim, device=device)
        with self.assertRaises(IndexError):
            a.index_copy_(1, idx, c)

        # Too small (negative indices)
        idx = torch.full((idx_dim,), -1, device=device)
        with self.assertRaises(IndexError):
            a.index_copy_(1, idx, c)

        # Too small (very negative indices) - they should be unsupported even
        # when support for negative indices is implemented for index_copy_
        idx = torch.full((idx_dim,), -tgt_dim - 1, device=device)
        with self.assertRaises(IndexError):
            a.index_copy_(1, idx, c)

    def _prepare_data_for_index_copy_and_add_deterministic(
        self, dim: int, device: torch.device
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        assert dim >= 0 and dim < 3
        a = [5, 4, 3]
        a[dim] = 2000
        x = torch.zeros(a, device=device)
        b = a.copy()
        elems = a[dim] * 20
        b[dim] = elems
        src = torch.rand(b, device=device)
        index = torch.randint(a[dim], (elems,), device=device)
        return (x, index, src)

    @onlyNativeDeviceTypes
    def test_index_copy_deterministic(self, device: torch.device) -> None:
        for dim in range(3):
            x, index, src = self._prepare_data_for_index_copy_and_add_deterministic(
                dim, device
            )
            with DeterministicGuard(True):
                y0 = torch.index_copy(x, dim, index, src)

            x0 = x.detach().clone()
            index_list = index.tolist()
            for i in range(len(index_list)):
                if dim == 0:
                    x0[index_list[i], :, :] = src[i, :, :]
                elif dim == 1:
                    x0[:, index_list[i], :] = src[:, i, :]
                elif dim == 2:
                    x0[:, :, index_list[i]] = src[:, :, i]

            self.assertEqual(x0, y0, atol=0, rtol=0)

    @onlyNativeDeviceTypes
    def test_index_add_deterministic(self, device: torch.device) -> None:
        for dim in range(3):
            x, index, src = self._prepare_data_for_index_copy_and_add_deterministic(
                dim, device
            )
            alpha = random.random() + 1
            # on CPU it should be deterministic regardless of the deterministic mode
            with DeterministicGuard(True):
                y0 = torch.index_add(x, dim, index, src, alpha=alpha)
                for _ in range(3):
                    y = torch.index_add(x, dim, index, src, alpha=alpha)
                    self.assertEqual(y, y0, atol=0, rtol=0)

            with DeterministicGuard(False):
                for _ in range(3):
                    y_nd = torch.index_add(x, dim, index, src, alpha=alpha)
                    self.assertEqual(y_nd, y0, atol=1e-3, rtol=1e-5)

    @dtypes(*all_types_and_complex_and(torch.half, torch.bool, torch.bfloat16))
    @skipIfMPS
    def test_index_fill(self, device, dtype):
        x = torch.tensor([[1, 2], [4, 5]], dtype=dtype, device=device)
        index = torch.tensor([0], device=device)
        x.index_fill_(1, index, 0)
        self.assertEqual(x, torch.tensor([[0, 2], [0, 5]], dtype=dtype, device=device))
        if not x.is_complex() and not device == "meta":
            with self.assertRaisesRegex(RuntimeError, r"Scalar"):
                x.index_fill_(1, index, 1 + 1j)
        # Make sure that the result stays 0-dim while applied to
        # a 0-dim input
        x = torch.tensor(1, dtype=dtype, device=device)
        self.assertEqual(0, x.index_fill(0, index, -1).dim())
        self.assertEqual(0, x.index_fill_(0, index, -1).dim())

    # The test fails for zero-dimensional tensors on XLA
    @onlyNativeDeviceTypes
    @dtypes(*all_types_complex_float8_and(torch.half, torch.bool, torch.bfloat16))
    def test_index_select(self, device, dtype):
        num_src, num_out = 3, 5

        def make_arg(batch_sizes, n, dim, contig):
            size_arg = batch_sizes[:dim] + (n,) + batch_sizes[dim:]
            return make_tensor(
                size_arg,
                dtype=dtype,
                device=device,
                low=None,
                high=None,
                noncontiguous=not contig,
            )

        def ref_index_select(src, dim, idx):
            # some types not supported on numpy
            not_np_dtypes = (
                torch.bfloat16,
                torch.float8_e5m2,
                torch.float8_e5m2fnuz,
                torch.float8_e4m3fn,
                torch.float8_e4m3fnuz,
            )
            if dtype in not_np_dtypes:
                src = src.float()
            out = torch.from_numpy(
                np.take(src.cpu().numpy(), idx.cpu().numpy(), axis=dim)
            )
            if dtype in not_np_dtypes:
                out = out.to(device=device, dtype=dtype)
            return out

        for src_contig, idx_contig in product([True, False], repeat=2):
            for other_sizes in ((), (4, 5)):
                for dim in range(len(other_sizes)):
                    src = make_arg(other_sizes, num_src, dim, src_contig)
                    idx = make_tensor(
                        (num_out,),
                        dtype=torch.int64,
                        device=device,
                        low=0,
                        high=num_src,
                        noncontiguous=not idx_contig,
                    )
                    out = torch.index_select(src, dim, idx)
                    out2 = ref_index_select(src, dim, idx)
                    self.assertEqual(out, out2)

        for idx_type in (torch.int32, torch.int64):
            other_sizes = (3, 2)
            dim = 1
            src = make_arg(other_sizes, num_src, dim, True)
            idx = make_tensor(
                (num_out,),
                dtype=idx_type,
                device=device,
                low=0,
                high=num_src,
                noncontiguous=False,
            )
            out = torch.index_select(src, dim, idx)
            out2 = ref_index_select(src, dim, idx)
            self.assertEqual(out, out2)

        # Create the 4 possible combinations of scalar sizes for index / source
        scalars = (
            (
                make_tensor(size_s, dtype=dtype, device=device),
                torch.zeros(size_i, dtype=torch.int64, device=device),
            )
            for size_s, size_i in product([(), (1,)], repeat=2)
        )
        for source, idx in scalars:
            out = source.index_select(0, idx)
            self.assertEqual(out.item(), source.item())


# The tests below are from NumPy test_indexing.py with some modifications to
# make them compatible with PyTorch. It's licensed under the BDS license below:
#
# Copyright (c) 2005-2017, NumPy Developers.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#        notice, this list of conditions and the following disclaimer.
#
#     * Redistributions in binary form must reproduce the above
#        copyright notice, this list of conditions and the following
#        disclaimer in the documentation and/or other materials provided
#        with the distribution.
#
#     * Neither the name of the NumPy Developers nor the names of any
#        contributors may be used to endorse or promote products derived
#        from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


class NumpyTests(TestCase):
    def test_index_no_floats(self, device):
        a = torch.tensor([[[5.0]]], device=device)

        self.assertRaises(IndexError, lambda: a[0.0])
        self.assertRaises(IndexError, lambda: a[0, 0.0])
        self.assertRaises(IndexError, lambda: a[0.0, 0])
        self.assertRaises(IndexError, lambda: a[0.0, :])
        self.assertRaises(IndexError, lambda: a[:, 0.0])
        self.assertRaises(IndexError, lambda: a[:, 0.0, :])
        self.assertRaises(IndexError, lambda: a[0.0, :, :])
        self.assertRaises(IndexError, lambda: a[0, 0, 0.0])
        self.assertRaises(IndexError, lambda: a[0.0, 0, 0])
        self.assertRaises(IndexError, lambda: a[0, 0.0, 0])
        self.assertRaises(IndexError, lambda: a[-1.4])
        self.assertRaises(IndexError, lambda: a[0, -1.4])
        self.assertRaises(IndexError, lambda: a[-1.4, 0])
        self.assertRaises(IndexError, lambda: a[-1.4, :])
        self.assertRaises(IndexError, lambda: a[:, -1.4])
        self.assertRaises(IndexError, lambda: a[:, -1.4, :])
        self.assertRaises(IndexError, lambda: a[-1.4, :, :])
        self.assertRaises(IndexError, lambda: a[0, 0, -1.4])
        self.assertRaises(IndexError, lambda: a[-1.4, 0, 0])
        self.assertRaises(IndexError, lambda: a[0, -1.4, 0])
        # self.assertRaises(IndexError, lambda: a[0.0:, 0.0])
        # self.assertRaises(IndexError, lambda: a[0.0:, 0.0,:])

    def test_none_index(self, device):
        # `None` index adds newaxis
        a = tensor([1, 2, 3], device=device)
        self.assertEqual(a[None].dim(), a.dim() + 1)

    def test_empty_tuple_index(self, device):
        # Empty tuple index creates a view
        a = tensor([1, 2, 3], device=device)
        self.assertEqual(a[()], a)
        self.assertEqual(a[()].data_ptr(), a.data_ptr())

    def test_empty_fancy_index(self, device):
        # Empty list index creates an empty array
        a = tensor([1, 2, 3], device=device)
        self.assertEqual(a[[]], torch.tensor([], dtype=torch.long, device=device))

        b = tensor([], device=device).long()
        self.assertEqual(a[[]], torch.tensor([], dtype=torch.long, device=device))

        b = tensor([], device=device).float()
        self.assertRaises(IndexError, lambda: a[b])

    def test_ellipsis_index(self, device):
        a = tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], device=device)
        self.assertIsNot(a[...], a)
        self.assertEqual(a[...], a)
        # `a[...]` was `a` in numpy <1.9.
        self.assertEqual(a[...].data_ptr(), a.data_ptr())

        # Slicing with ellipsis can skip an
        # arbitrary number of dimensions
        self.assertEqual(a[0, ...], a[0])
        self.assertEqual(a[0, ...], a[0, :])
        self.assertEqual(a[..., 0], a[:, 0])

        # In NumPy, slicing with ellipsis results in a 0-dim array. In PyTorch
        # we don't have separate 0-dim arrays and scalars.
        self.assertEqual(a[0, ..., 1], torch.tensor(2, device=device))

        # Assignment with `(Ellipsis,)` on 0-d arrays
        b = torch.tensor(1)
        b[(Ellipsis,)] = 2
        self.assertEqual(b, 2)

    def test_single_int_index(self, device):
        # Single integer index selects one row
        a = tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], device=device)

        self.assertEqual(a[0], [1, 2, 3])
        self.assertEqual(a[-1], [7, 8, 9])

        # Index out of bounds produces IndexError
        self.assertRaises(IndexError, a.__getitem__, 1 << 30)
        # Index overflow produces Exception  NB: different exception type
        self.assertRaises(Exception, a.__getitem__, 1 << 64)

    def test_single_bool_index(self, device):
        # Single boolean index
        a = tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], device=device)

        self.assertEqual(a[True], a[None])
        self.assertEqual(a[False], a[None][0:0])

    def test_boolean_shape_mismatch(self, device):
        arr = torch.ones((5, 4, 3), device=device)

        index = tensor([True], device=device)
        self.assertRaisesRegex(IndexError, "mask", lambda: arr[index])

        index = tensor([False] * 6, device=device)
        self.assertRaisesRegex(IndexError, "mask", lambda: arr[index])

        index = torch.ByteTensor(4, 4).to(device).zero_()
        self.assertRaisesRegex(IndexError, "mask", lambda: arr[index])
        self.assertRaisesRegex(IndexError, "mask", lambda: arr[(slice(None), index)])

    def test_boolean_indexing_onedim(self, device):
        # Indexing a 2-dimensional array with
        # boolean array of length one
        a = tensor([[0.0, 0.0, 0.0]], device=device)
        b = tensor([True], device=device)
        self.assertEqual(a[b], a)
        # boolean assignment
        a[b] = 1.0
        self.assertEqual(a, tensor([[1.0, 1.0, 1.0]], device=device))

    # https://github.com/pytorch/pytorch/issues/127003
    @xfailIfTorchDynamo
    def test_boolean_assignment_value_mismatch(self, device):
        # A boolean assignment should fail when the shape of the values
        # cannot be broadcast to the subscription. (see also gh-3458)
        a = torch.arange(0, 4, device=device)

        def f(a, v):
            a[a > -1] = tensor(v).to(device)

        self.assertRaisesRegex(Exception, "shape mismatch", f, a, [])
        self.assertRaisesRegex(Exception, "shape mismatch", f, a, [1, 2, 3])
        self.assertRaisesRegex(Exception, "shape mismatch", f, a[:1], [1, 2, 3])

    def test_boolean_indexing_twodim(self, device):
        # Indexing a 2-dimensional array with
        # 2-dimensional boolean array
        a = tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], device=device)
        b = tensor(
            [[True, False, True], [False, True, False], [True, False, True]],
            device=device,
        )
        self.assertEqual(a[b], tensor([1, 3, 5, 7, 9], device=device))
        self.assertEqual(a[b[1]], tensor([[4, 5, 6]], device=device))
        self.assertEqual(a[b[0]], a[b[2]])

        # boolean assignment
        a[b] = 0
        self.assertEqual(a, tensor([[0, 2, 0], [4, 0, 6], [0, 8, 0]], device=device))

    def test_boolean_indexing_weirdness(self, device):
        # Weird boolean indexing things
        a = torch.ones((2, 3, 4), device=device)
        self.assertEqual((0, 2, 3, 4), a[False, True, ...].shape)
        self.assertEqual(
            torch.ones(1, 2, device=device), a[True, [0, 1], True, True, [1], [[2]]]
        )
        self.assertRaises(IndexError, lambda: a[False, [0, 1], ...])

    def test_boolean_indexing_weirdness_tensors(self, device):
        # Weird boolean indexing things
        false = torch.tensor(False, device=device)
        true = torch.tensor(True, device=device)
        a = torch.ones((2, 3, 4), device=device)
        self.assertEqual((0, 2, 3, 4), a[False, True, ...].shape)
        self.assertEqual(
            torch.ones(1, 2, device=device), a[true, [0, 1], true, true, [1], [[2]]]
        )
        self.assertRaises(IndexError, lambda: a[false, [0, 1], ...])

    def test_boolean_indexing_alldims(self, device):
        true = torch.tensor(True, device=device)
        a = torch.ones((2, 3), device=device)
        self.assertEqual((1, 2, 3), a[True, True].shape)
        self.assertEqual((1, 2, 3), a[true, true].shape)

    def test_boolean_list_indexing(self, device):
        # Indexing a 2-dimensional array with
        # boolean lists
        a = tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], device=device)
        b = [True, False, False]
        c = [True, True, False]
        self.assertEqual(a[b], tensor([[1, 2, 3]], device=device))
        self.assertEqual(a[b, b], tensor([1], device=device))
        self.assertEqual(a[c], tensor([[1, 2, 3], [4, 5, 6]], device=device))
        self.assertEqual(a[c, c], tensor([1, 5], device=device))

    def test_everything_returns_views(self, device):
        # Before `...` would return a itself.
        a = tensor([5], device=device)

        self.assertIsNot(a, a[()])
        self.assertIsNot(a, a[...])
        self.assertIsNot(a, a[:])

    def test_broaderrors_indexing(self, device):
        a = torch.zeros(5, 5, device=device)
        self.assertRaisesRegex(
            IndexError, "shape mismatch", a.__getitem__, ([0, 1], [0, 1, 2])
        )
        self.assertRaisesRegex(
            IndexError, "shape mismatch", a.__setitem__, ([0, 1], [0, 1, 2]), 0
        )

    def test_trivial_fancy_out_of_bounds(self, device):
        a = torch.zeros(5, device=device)
        ind = torch.ones(20, dtype=torch.int64, device=device)
        if a.is_cuda:
            raise unittest.SkipTest("CUDA asserts instead of raising an exception")
        ind[-1] = 10
        self.assertRaises(IndexError, a.__getitem__, ind)
        self.assertRaises(IndexError, a.__setitem__, ind, 0)
        ind = torch.ones(20, dtype=torch.int64, device=device)
        ind[0] = 11
        self.assertRaises(IndexError, a.__getitem__, ind)
        self.assertRaises(IndexError, a.__setitem__, ind, 0)

    def test_index_is_larger(self, device):
        # Simple case of fancy index broadcasting of the index.
        a = torch.zeros((5, 5), device=device)
        a[[[0], [1], [2]], [0, 1, 2]] = tensor([2.0, 3.0, 4.0], device=device)

        self.assertTrue((a[:3, :3] == tensor([2.0, 3.0, 4.0], device=device)).all())

    def test_broadcast_subspace(self, device):
        a = torch.zeros((100, 100), device=device)
        v = torch.arange(0.0, 100, device=device)[:, None]
        b = torch.arange(99, -1, -1, device=device).long()
        a[b] = v
        expected = b.float().unsqueeze(1).expand(100, 100)
        self.assertEqual(a, expected)

    def test_truncate_leading_1s(self, device):
        col_max = torch.randn(1, 4)
        kernel = col_max.T * col_max  # [4, 4] tensor
        kernel2 = kernel.clone()
        # Set the diagonal
        kernel[range(len(kernel)), range(len(kernel))] = torch.square(col_max)
        torch.diagonal(kernel2).copy_(torch.square(col_max.view(4)))
        self.assertEqual(kernel, kernel2)


instantiate_device_type_tests(TestIndexing, globals(), except_for="meta")
instantiate_device_type_tests(NumpyTests, globals(), except_for="meta")

if __name__ == "__main__":
    run_tests()
