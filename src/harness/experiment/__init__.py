"""Experiment: the controlled fictional rig — the centerpiece artifact.

A fictional media-catalog API (studio -> series -> season -> episode -> asset)
with a seeded generator, answer keys, and a programmatic grader. It is where the
research claims come from, and the only place these can be measured at all:

  - the Z0 contamination gate
  - the four-route harm asymmetry probe (PATCH / PUT / sub-collection POST /
    action :archive, same change, different blast radius)
  - matched-pair write penalties
  - the error/response affordance sweep

No real API can host any of them — you cannot ask a production server to re-issue
the same state change four ways.

This package is a *consumer* of ``harness.engine``, never the other way round,
and it reaches the engine only through the public task-pack interface.

Empty at P0; built at P3.
"""
