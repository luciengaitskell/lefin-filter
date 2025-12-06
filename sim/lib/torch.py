import torch
from torch import Tensor


def int8_torch_to_packed(value: Tensor) -> int:
    assert value.dtype == torch.int8, "Input tensor must be of dtype int8"
    packed = 0
    for i, v in enumerate(value):
        packed |= (int(v.item()) & 0xFF) << (i * 8)
    return packed

def long_torch_to_packed(value: Tensor, value_bit_width: int) -> int:
    assert value.dtype == torch.long, "Input tensor must be of dtype long"
    packed = 0
    for i, v in enumerate(value):
        packed |= (int(v.item()) & ((1 << value_bit_width) - 1)) << (
            i * value_bit_width
        )
    return packed

def packed_to_int8_torch(value: int, length: int) -> Tensor:
    values = []
    for i in range(length):
        byte = (value >> (i * 8)) & 0xFF
        if byte >= 0x80:
            byte -= 0x100
        values.append(byte)
    return torch.tensor(values, dtype=torch.int8)


def packed_to_long_torch(value: int, value_bit_width: int, length: int) -> Tensor:
    values = []
    for i in range(length):
        byte = (value >> (i * value_bit_width)) & ((1 << value_bit_width) - 1)
        sign_bit = 1 << (value_bit_width - 1)
        if byte & sign_bit:
            byte -= 1 << value_bit_width
        values.append(byte)
    return torch.tensor(values, dtype=torch.long)
