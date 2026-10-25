from __future__ import annotations

from typing import List, Tuple
import secrets


HEX_512_LEN = 128
MASK_512 = (1 << 512) - 1


def random_block() -> str:
    """Возвращает случайный 512-битный блок в hex-представлении."""
    return secrets.token_hex(64)


def nice(st: str, n: int) -> str:
    return st.zfill(len(st) + ((n - len(st) % n) % n))


def is_binary_string(s: str) -> bool:
    return set(s) <= {"0", "1"}


def is_hex_string(s: str) -> bool:
    return set(s.upper()) <= set("0123456789ABCDEF")


def _pad_message_bits(bits: str) -> Tuple[str, int]:
    """Дополняет сообщение слева по схеме 0…01 || M и возвращает биты с длиной последнего блока согласно RFC 6986."""
    original_len = len(bits)
    if original_len == 0:
        return "1".zfill(512), 0

    remainder = original_len % 512
    bits = "0" * (511 - remainder) + "1" + bits
    return bits, remainder


def string_to_hex(s: str) -> tuple[str, int]:
    try:
        binary = "".join(format(b, "08b") for b in s.encode("windows-1251"))
    except UnicodeEncodeError as exc:
        raise ValueError('Введён символ, отсутствующий в кодировке "windows-1251".') from exc
    padded, last_len = _pad_message_bits(binary)
    return f"{int(padded, 2):0{len(padded) // 4}x}", last_len


def hex_to_string(hex_string: str, len_M: int) -> str:
    bits = "".join(format(int(c, 16), "04b") for c in hex_string)
    if len_M:
        orig_bits = bits[-len_M:]
    else:
        orig_bits = ""
    if len(orig_bits) % 8:
        raise ValueError("Длина исходного сообщения не кратна 8 битам.")
    byte_vals = [int(orig_bits[i:i + 8], 2) for i in range(0, len(orig_bits), 8)]
    try:
        return bytes(byte_vals).decode("windows-1251")
    except UnicodeDecodeError as exc:
        raise ValueError("Не удалось декодировать байты как windows-1251") from exc


def binary_string_to_hex(binary: str) -> tuple[str, int]:
    if not is_binary_string(binary):
        raise ValueError("Ожидалась двоичная строка.")
    padded, last_len = _pad_message_bits(binary)
    return f"{int(padded, 2):0{len(padded) // 4}x}", last_len


def hex_to_bin(x: str) -> str:
    if not x:
        return ""
    return bin(int(x, 16))[2:].zfill(len(x) * 4)


def validate_length_pow_2(length: int) -> bool:
    return length > 0 and (length & (length - 1)) == 0


def xor_mod2(result: List[int]) -> int:
    return sum(result) % 2


def dec_to_bin_array(n: int, k: int = 8) -> List[int]:
    b = bin(n)[2:]
    padded = b.zfill((len(b) + k - 1) // k * k)
    return [int(bit) for bit in padded]


S_box = [252, 238, 221, 17, 207, 110, 49, 22, 251, 196, 250, 218, 35, 197, 4, 77, 233, 119, 240,
         219, 147, 46, 153, 186, 23, 54, 241, 187, 20, 205, 95, 193, 249, 24, 101, 90, 226, 92, 239,
         33, 129, 28, 60, 66, 139, 1, 142, 79, 5, 132, 2, 174, 227, 106, 143, 160, 6, 11, 237, 152, 127,
         212, 211, 31, 235, 52, 44, 81, 234, 200, 72, 171, 242, 42, 104, 162, 253, 58, 206, 204, 181,
         112, 14, 86, 8, 12, 118, 18, 191, 114, 19, 71, 156, 183, 93, 135, 21, 161, 150, 41, 16, 123,
         154, 199, 243, 145, 120, 111, 157, 158, 178, 177, 50, 117, 25, 61, 255, 53, 138, 126, 109,
         84, 198, 128, 195, 189, 13, 87, 223, 245, 36, 169, 62, 168, 67, 201, 215, 121, 214, 246, 124,
         34, 185, 3, 224, 15, 236, 222, 122, 148, 176, 188, 220, 232, 40, 80, 78, 51, 10, 74, 167, 151,
         96, 115, 30, 0, 98, 68, 26, 184, 56, 130, 100, 159, 38, 65, 173, 69, 70, 146, 39, 94, 85, 47,
         140, 163, 165, 125, 105, 213, 149, 59, 7, 88, 179, 64, 134, 172, 29, 247, 48, 55, 107, 228,
         136, 217, 231, 137, 225, 27, 131, 73, 76, 63, 248, 254, 141, 83, 170, 144, 202, 216, 133, 97,
         32, 113, 103, 164, 45, 43, 9, 91, 203, 155, 37, 208, 190, 229, 108, 82, 89, 166, 116, 210,
         230, 244, 180, 192, 209, 102, 175, 194, 57, 75, 99, 182]

P_box = [0, 8, 16, 24, 32, 40, 48, 56, 1, 9, 17, 25, 33, 41, 49, 57, 2, 10, 18, 26, 34, 42, 50, 58,
         3, 11, 19, 27, 35, 43, 51, 59, 4, 12, 20, 28, 36, 44, 52, 60, 5, 13, 21, 29, 37, 45, 53, 61,
         6, 14, 22, 30, 38, 46, 54, 62, 7, 15, 23, 31, 39, 47, 55, 63]

L_box = ['8e20faa72ba0b470', '47107ddd9b505a38', 'ad08b0e0c3282d1c', 'd8045870ef14980e',
         '6c022c38f90a4c07', '3601161cf205268d', '1b8e0b0e798c13c8', '83478b07b2468764',
         'a011d380818e8f40', '5086e740ce47c920', '2843fd2067adea10', '14aff010bdd87508',
         '0ad97808d06cb404', '05e23c0468365a02', '8c711e02341b2d01', '46b60f011a83988e',
         '90dab52a387ae76f', '486dd4151c3dfdb9', '24b86a840e90f0d2', '125c354207487869',
         '092e94218d243cba', '8a174a9ec8121e5d', '4585254f64090fa0', 'accc9ca9328a8950',
         '9d4df05d5f661451', 'c0a878a0a1330aa6', '60543c50de970553', '302a1e286fc58ca7',
         '18150f14b9ec46dd', '0c84890ad27623e0', '0642ca05693b9f70', '0321658cba93c138',
         '86275df09ce8aaa8', '439da0784e745554', 'afc0503c273aa42a', 'd960281e9d1d5215',
         'e230140fc0802984', '71180a8960409a42', 'b60c05ca30204d21', '5b068c651810a89e',
         '456c34887a3805b9', 'ac361a443d1c8cd2', '561b0d22900e4669', '2b838811480723ba',
         '9bcf4486248d9f5d', 'c3e9224312c8c1a0', 'effa11af0964ee50', 'f97d86d98a327728',
         'e4fa2054a80b329c', '727d102a548b194e', '39b008152acb8227', '9258048415eb419d',
         '492c024284fbaec0', 'aa16012142f35760', '550b8e9e21f7a530', 'a48b474f9ef5dc18',
         '70a6a56e2440598e', '3853dc371220a247', '1ca76e95091051ad', '0edd37c48a08a6d8',
         '07e095624504536c', '8d70c431ac02a736', 'c83862965601dd1b', '641c314b2b8ee083']

C_list = [
    'b1085bda1ecadae9ebcb2f81c0657c1f2f6a76432e45d016714eb88d7585c4fc4b7ce09192676901a2422a08a460d31505767436cc744d23dd806559f2a64507',
    '6fa3b58aa99d2f1a4fe39d460f70b5d7f3feea720a232b9861d55e0f16b501319ab5176b12d699585cb561c2db0aa7ca55dda21bd7cbcd56e679047021b19bb7',
    'f574dcac2bce2fc70a39fc286a3d843506f15e5f529c1f8bf2ea7514b1297b7bd3e20fe490359eb1c1c93a376062db09c2b6f443867adb31991e96f50aba0ab2',
    'ef1fdfb3e81566d2f948e1a05d71e4dd488e857e335c3c7d9d721cad685e353fa9d72c82ed03d675d8b71333935203be3453eaa193e837f1220cbebc84e3d12e',
    '4bea6bacad4747999a3f410c6ca923637f151c1f1686104a359e35d7800fffbdbfcd1747253af5a3dfff00b723271a167a56a27ea9ea63f5601758fd7c6cfe57',
    'ae4faeae1d3ad3d96fa4c33b7a3039c02d66c4f95142a46c187f9ab49af08ec6cffaa6b71c9ab7b40af21f66c2bec6b6bf71c57236904f35fa68407a46647d6e',
    'f4c70e16eeaac5ec51ac86febf240954399ec6c7e6bf87c9d3473e33197a93c90992abc52d822c3706476983284a05043517454ca23c4af38886564d3a14d493',
    '9b1f5b424d93c9a703e7aa020c6e41414eb7f8719c36de1e89b4443b4ddbc49af4892bcb929b069069d18d2bd1a5c42f36acc2355951a8d9a47f0dd4bf02e71e',
    '378f5a541631229b944c9ad8ec165fde3a7d3a1b258942243cd955b7e00d0984800a440bdbb2ceb17b2b8a9aa6079c540e38dc92cb1f2a607261445183235adb',
    'abbedea680056f52382ae548b2e4f3f38941e71cff8a78db1fffe18a1b3361039fe76702af69334b7a1e6c303b7652f43698fad1153bb6c374b4c7fb98459ced',
    '7bcd9ed0efc889fb3002c6cd635afe94d8fa6bbbebab076120018021148466798a1d71efea48b9caefbacd1d7d476e98dea2594ac06fd85d6bcaa4cd81f32d1b',
    '378ee767f11631bad21380b00449b17acda43c32bcdf1d77f82012d430219f9b5d80ef9d1891cc86e71da4aa88e12852faf417d5d9b21b9948bc924af11bd720'
]

L_box_optimized = [int(x, 16) for x in L_box]


def _require_hex_512(value: str, name: str) -> str:
    value = value.lower()
    if len(value) != HEX_512_LEN or not is_hex_string(value):
        raise ValueError(f"{name} должен быть 512-битной hex-строкой длины 128 символов.")
    return value


def hex_xor(a: str, b: str) -> str:
    if len(a) != len(b):
        raise ValueError("Длины строк не совпадают для XOR.")
    return f"{int(a, 16) ^ int(b, 16):0{len(a)}x}"


def S(a: str) -> str:
    return ''.join(f"{S_box[int(a[i:i + 2], 16)]:02x}" for i in range(0, len(a), 2))


def P(a: str) -> str:
    bytes_hex = [a[i:i + 2] for i in range(0, len(a), 2)]
    return ''.join(bytes_hex[P_box[i]] for i in range(64))


def L(a: str) -> str:
    if len(a) % 16:
        a = a.zfill(len(a) + (16 - len(a) % 16))
    result_blocks = []
    for i in range(0, len(a), 16):
        block_int = int(a[i:i + 16], 16)
        acc = 0
        for j in range(64):
            if (block_int >> (63 - j)) & 1:
                acc ^= L_box_optimized[j]
        result_blocks.append(f"{acc:016x}")
    return ''.join(result_blocks)


def LPS(a: str) -> str:
    return L(P(S(a)))


def E(key: str, message: str, rounds: int = 12) -> str:
    """Вычисляет преобразование шифрования E(K, m) из раздела 8 RFC 6986."""
    key = _require_hex_512(key, "K")
    state = _require_hex_512(message, "m")
    if not 1 <= rounds <= 12:
        raise ValueError("rounds должен быть от 1 до 12.")
    for i in range(rounds):
        state = LPS(hex_xor(key, state))
        key = LPS(hex_xor(key, C_list[i]))
    return hex_xor(key, state)


def gost_compress(m: str, h: str, N: int | str, rounds: int = 12) -> str:
    """Чистая функция сжатия g_N(h, m) из используемой в проекте реализации."""
    m = _require_hex_512(m, "m")
    h = _require_hex_512(h, "h")
    if isinstance(N, int):
        if N < 0 or N > MASK_512:
            raise ValueError("N должен лежать в диапазоне [0, 2^512-1].")
        N_hex = f"{N:0128x}"
    else:
        N_hex = _require_hex_512(N, "N")
    if not (1 <= rounds <= 12):
        raise ValueError("rounds должен быть от 1 до 12.")

    K = LPS(hex_xor(h, N_hex))
    return hex_xor(hex_xor(E(K, m, rounds), h), m)


def add_mod_512(a: str, b: str) -> str:
    return f"{(int(a, 16) + int(b, 16)) & MASK_512:0128x}"


def finalize_state(h: str, N: int | str, sigma: str, rounds: int = 12) -> str:
    if isinstance(N, int):
        N_hex = f"{N & MASK_512:0128x}"
    else:
        N_hex = _require_hex_512(N, "N")
    sigma = _require_hex_512(sigma, "sigma")
    h = gost_compress(N_hex, h, 0, rounds)
    h = gost_compress(sigma, h, 0, rounds)
    return h


class HashCalculator:
    """Вычисляет полную хэш-функцию ГОСТ с корректным учётом N и Σ отдельно от модели части хэш-кода."""

    def __init__(self, choice, M_format, M, compress_rounds=12):
        self.choice = choice
        self.M_format = M_format
        self.M_len = 0
        self.M = M
        self.compress_rounds = compress_rounds
        self.h = '0' * 128
        if choice == '0':
            self.h = '01' * 64
        self.N = '0' * 128
        self.total = '0' * 128
        self.check_input()

    def hex_xor(self, char1, char2):
        return hex_xor(char1, char2)

    def X(self, k, a):
        return hex_xor(k, a)

    def S(self, a):
        return S(a)

    def P(self, a):
        return P(a)

    def L(self, a):
        return L(a)

    def MSB(self, M_t):
        return M_t[:64]

    def compression_function(self, m, h, N):
        return gost_compress(m, h, N, self.compress_rounds)

    def check_input(self):
        if self.M_format == 'bin' and not is_binary_string(self.M):
            raise ValueError("Некорректная двоичная строка.")
        if self.M_format == 'hex' and not is_hex_string(self.M.upper()):
            raise ValueError("Некорректная hex-строка.")
        converter = {
            'str': string_to_hex,
            'bin': binary_string_to_hex,
            'hex': lambda m: binary_string_to_hex(hex_to_bin(m))
        }.get(self.M_format)
        if converter is None:
            raise ValueError("M_format должен быть 'str', 'bin' или 'hex'.")
        self.M, self.M_len = converter(self.M)

    def run(self):
        work = self.M
        blocks = []
        while len(work) > 128:
            blocks.append(work[-128:])
            work = work[:-128]
        blocks.append(work.zfill(128))

        h = self.h
        N_int = 0
        sigma = '0' * 128

        for index, block in enumerate(blocks):
            is_last_processed = index == len(blocks) - 1
            block_bit_len = self.M_len if is_last_processed else 512
            h = gost_compress(block, h, N_int, self.compress_rounds)
            N_int = (N_int + block_bit_len) & MASK_512
            sigma = add_mod_512(sigma, block)

        self.N = f"{N_int:0128x}"
        self.total = sigma
        self.h = finalize_state(h, N_int, sigma, self.compress_rounds)
        return self.h if self.choice == '1' else self.MSB(self.h)

    def test_root(self, h, N: int | str | None = None, total: str | None = None):
        """Финализирует внутреннее состояние с заданными N и полной контрольной суммой."""
        if N is None:
            N = self.M_len
        if total is None:
            total = self.M[-128:].zfill(128)
        result = finalize_state(h, N, total, self.compress_rounds)
        return result if self.choice == '1' else self.MSB(result)
