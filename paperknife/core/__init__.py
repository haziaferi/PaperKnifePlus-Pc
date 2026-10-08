"""
paperknife.core
The PDF and file work of every tool, with no user interface.

Each function takes its inputs as plain values, a threading.Event *stop* it checks
between steps, and a *progress(fraction)* callback it may call from the worker
thread.  The user interface (CustomTkinter today, Qt after the switch) reads its
widgets, asks its dialogs, then runs one of these in a background job.
"""
