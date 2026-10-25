from __future__ import annotations

import math
import random
import secrets
from dataclasses import dataclass
from typing import Sequence, Tuple

from HashCalculator import gost_compress


LEGACY_MODEL_NAME = "reduced-prefix-state-v2"
MODEL_NAME = "reduced-h-sigma-state-v3"
FORMAT_VERSION = 3
LEGACY_FORMAT_VERSION = 2
MAX_SIGMA_BITS = 64  # Оптимизированное ядро C++ поддерживает s ≤ 64.


def validate_truncate_bits(truncate_bits: int) -> None:
    if truncate_bits <= 0 or truncate_bits > 512 or truncate_bits % 4 != 0:
        raise ValueError("truncate_bits должен быть кратен 4 и лежать в диапазоне 4..512.")


def validate_sigma_bits(sigma_bits: int) -> None:
    if sigma_bits < 0 or sigma_bits > MAX_SIGMA_BITS:
        raise ValueError(f"sigma_bits должен лежать в диапазоне 0..{MAX_SIGMA_BITS}.")


def sigma_mask(sigma_bits: int) -> int:
    validate_sigma_bits(sigma_bits)
    return (1 << sigma_bits) - 1 if sigma_bits else 0


def _validate_block_hex(block: str) -> str:
    block = block.lower()
    if len(block) != 128:
        raise ValueError("Блок должен быть 512-битной hex-строкой длины 128 символов.")
    int(block, 16)
    return block


def block_low_bits(block: str, sigma_bits: int) -> int:
    """Возвращает младшие s бит 512-битного блока сообщения."""
    validate_sigma_bits(sigma_bits)
    if sigma_bits == 0:
        return 0
    block = _validate_block_hex(block)
    return int(block[-16:], 16) & sigma_mask(sigma_bits)


def update_sigma_reduced(sigma_value: int, block: str, sigma_bits: int) -> int:
    """Вычисляет часть контрольной суммы (σ + m) mod 2^s."""
    validate_sigma_bits(sigma_bits)
    if sigma_bits == 0:
        return 0
    mask = sigma_mask(sigma_bits)
    return (int(sigma_value) + block_low_bits(block, sigma_bits)) & mask


def required_block_low_bits(current_sigma: int, target_sigma: int, sigma_bits: int) -> int:
    validate_sigma_bits(sigma_bits)
    if sigma_bits == 0:
        return 0
    mask = sigma_mask(sigma_bits)
    return (int(target_sigma) - int(current_sigma)) & mask


def set_low_sigma_bits(block: str, required_low: int, sigma_bits: int) -> str:
    """Устанавливает младшие s бит блока в правом конце шестнадцатеричной записи."""
    validate_sigma_bits(sigma_bits)
    block = _validate_block_hex(block)
    if sigma_bits == 0:
        return block
    mask = sigma_mask(sigma_bits)
    value = int(block, 16)
    value = (value & ~mask) | (int(required_low) & mask)
    return f"{value:0128x}"


def constrained_random_block(
    current_sigma: int,
    target_sigma: int,
    sigma_bits: int,
    rng: random.Random | None = None,
) -> str:
    """Создаёт случайный 512-битный блок с заданным переходом части контрольной суммы."""
    validate_sigma_bits(sigma_bits)
    if rng is None:
        block = secrets.token_hex(64)
    else:
        block = f"{rng.getrandbits(512):0128x}"
    required = required_block_low_bits(current_sigma, target_sigma, sigma_bits)
    return set_low_sigma_bits(block, required, sigma_bits)


def process_sigma_blocks(blocks: Sequence[str], sigma_bits: int, initial_sigma: int = 0) -> int:
    validate_sigma_bits(sigma_bits)
    sigma_value = int(initial_sigma) & sigma_mask(sigma_bits)
    for block in blocks:
        sigma_value = update_sigma_reduced(sigma_value, block, sigma_bits)
    return sigma_value


def truncate_state(full_state: str, truncate_bits: int) -> str:
    validate_truncate_bits(truncate_bits)
    return full_state[:truncate_bits // 4].lower()


def embed_reduced_state(state: str, truncate_bits: int) -> str:
    validate_truncate_bits(truncate_bits)
    expected = truncate_bits // 4
    state = state.lower()
    if len(state) != expected:
        raise ValueError(f"Редуцированное состояние должно иметь {expected} hex-символов.")
    int(state, 16)
    return state + "0" * (128 - expected)


def random_reduced_state(truncate_bits: int, rng: random.Random | None = None) -> str:
    validate_truncate_bits(truncate_bits)
    nbytes = math.ceil(truncate_bits / 8)
    value = rng.getrandbits(truncate_bits) if rng is not None else int.from_bytes(secrets.token_bytes(nbytes), "big") & ((1 << truncate_bits) - 1)
    return f"{value:0{truncate_bits // 4}x}"


@dataclass(frozen=True)
class DiamondState:
    """Хранит состояние из части хэш-кода h_n и части контрольной суммы Σ mod 2^s."""

    h: str
    sigma: int = 0


@dataclass(frozen=True)
class ReducedGostModel:
    """Вычисляет первые n бит g_N дополненного состояния, обновляя часть контрольной суммы отдельно."""

    truncate_bits: int
    rounds: int = 12

    def __post_init__(self) -> None:
        validate_truncate_bits(self.truncate_bits)
        if not (1 <= self.rounds <= 12):
            raise ValueError("rounds должен быть в диапазоне 1..12.")

    @property
    def zero_state(self) -> str:
        return "0" * (self.truncate_bits // 4)

    def transition(self, block: str, state: str, N: int) -> str:
        full_h = embed_reduced_state(state, self.truncate_bits)
        full_out = gost_compress(block, full_h, N, self.rounds)
        return truncate_state(full_out, self.truncate_bits)

    def transition_pair(
        self,
        block: str,
        state: DiamondState,
        N: int,
        sigma_bits: int,
    ) -> DiamondState:
        return DiamondState(
            self.transition(block, state.h, N),
            update_sigma_reduced(state.sigma, block, sigma_bits),
        )

    def process_blocks(self, blocks: Sequence[str], start_N: int = 0) -> Tuple[str, int]:
        state = self.zero_state
        N = start_N
        for block in blocks:
            state = self.transition(block, state, N)
            N += 512
        return state, N

    def process_blocks_pair(
        self,
        blocks: Sequence[str],
        sigma_bits: int,
        start_N: int = 0,
        initial_sigma: int = 0,
    ) -> tuple[DiamondState, int]:
        state = DiamondState(self.zero_state, initial_sigma & sigma_mask(sigma_bits))
        N = start_N
        for block in blocks:
            state = self.transition_pair(block, state, N, sigma_bits)
            N += 512
        return state, N
