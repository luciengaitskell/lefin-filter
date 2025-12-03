import torch
from torch import Tensor


def int8_torch_to_packed(value: Tensor) -> int:
    assert value.dtype == torch.int8, "Input tensor must be of dtype int8"
    packed = 0
    for i, v in enumerate(value):
        packed |= (int(v.item()) & 0xFF) << (i * 8)
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

def list_to_bitpacked(value: list[int], bit_width: int) -> int:
    packed = 0
    for i, v in enumerate(value):
        # packed |= (v & ((1 << bit_width) - 1)) << (i * bit_width)
        #reversed of above
        packed |= (v & ((1 << bit_width) - 1)) << ((len(value) - 1 - i) * bit_width)
    # print each value in list as hex then print packed as hex
    print("Packing values:", value)
    print(f"Values:         {[hex(v & ((1 << bit_width) - 1)) for v in value]}")
    print(f"Packed:         {hex(packed)}")
    return packed