from dotenv import load_dotenv
import os

load_dotenv()


def get_secret(name):
    """
    A secret or setting, in priority order:
    1. Streamlit secrets (the platform's Secrets UI once deployed -
       never committed to the repo)
    2. .env / environment variable (local development)
    Returns None if it isn't set.
    """

    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass

    return os.getenv(name)
