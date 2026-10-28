"""Lazy public exports for the graph package.

Importing the checkpoint adapter must not initialize the full agent or import
Windows desktop dependencies. The public names remain available through lazy
attribute resolution for existing callers.
"""

__all__ = ["arun_agent", "initialize_agent", "run_agent"]


def __getattr__(name):
    if name in __all__:
        from src.graph import agent

        return getattr(agent, name)
    raise AttributeError(name)
