"""
Custom UI-komponenter til Juriitech — primært en smuk "thinking"-animation
der erstatter Streamlits default spinner med noget mere designvenligt.

Brug:
    from ui import thinking

    with thinking("Juriitech analyserer sagen..."):
        # Lav tungt arbejde her
        resultat = en_eller_anden_ai_kald()
"""

from contextlib import contextmanager

import streamlit as st


@contextmanager
def thinking(tekst="Juriitech arbejder..."):
    """
    Context manager der viser en Claude-inspireret pulsende gradient-prik
    med tekst ved siden af, mens kode i with-blokken kører. Forsvinder
    automatisk når blokken er færdig.
    """
    placeholder = st.empty()
    placeholder.markdown(
        f"""
        <div class="thinking-wrapper">
          <div class="thinking-dot"></div>
          <span class="thinking-text">{tekst}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()
