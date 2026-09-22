#include "test_visual_hull_cases.h"
#include "test_visual_hull_support.h"
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <vector>

namespace visual_hull_test
{

void
test_result_messages()
{
    assert(
        bpt_result_message(
            BPT_OK
        )
        != nullptr
    );

    assert(
        bpt_result_message(
            BPT_ERROR_INVALID_ARGUMENT
        )
        != nullptr
    );

    assert(
        bpt_result_message(
            BPT_ERROR_INTERNAL
        )
        != nullptr
    );
}


void
test_abi_version()
{
    assert(
        bpt_abi_version()
        == 1u
    );
}



} // namespace visual_hull_test
