#include "herding_link.hpp"

std::uintptr_t herding_link_odr_address() {
    return reinterpret_cast<std::uintptr_t>(&herding_link::find_link);
}
