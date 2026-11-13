"""Previous/Next paging for long lists, shared by every page."""

import streamlit as st

PAGE_SIZE = 25


def paginate(total, key, filters=None, page_size=PAGE_SIZE):
    """
    Shows "Showing 26–50 of 312" with Previous/Next buttons and
    returns the offset of the current page. Call it before loading
    the rows. Goes back to page 1 when `filters` changes.
    """

    pages = max(1, -(-total // page_size))
    state, sig = f"page_{key}", f"page_{key}_filters"

    if st.session_state.get(sig) != repr(filters):
        st.session_state[sig] = repr(filters)
        st.session_state[state] = 1

    page = min(st.session_state.get(state, 1), pages)

    prev_col, info_col, next_col = st.columns([1, 4, 1])
    if prev_col.button("← Previous", key=f"{key}_prev", disabled=page <= 1):
        page -= 1
    if next_col.button("Next →", key=f"{key}_next", disabled=page >= pages):
        page += 1
    st.session_state[state] = page

    first = (page - 1) * page_size
    info_col.caption(
        f"Showing {first + 1}–{min(first + page_size, total)} of {total}"
        if total else "Nothing to show")

    return first
