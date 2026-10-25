#include "grover_statevector.hpp"

const void* other_statevector_address() {
    return reinterpret_cast<const void*>(&grover_statevector::apply_diffusion);
}
