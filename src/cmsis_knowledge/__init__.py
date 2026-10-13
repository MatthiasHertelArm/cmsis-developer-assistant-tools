# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Build the knowledge a CMSIS pack ships for the CMSIS Developer Assistant.

A pack keeps its knowledge units as Markdown files in ``.knowledge/units/`` next to its PDSC; ``cmsis-knowledge
build`` checks them and writes ``.knowledge/knowledge.db``, the index the assistant's knowledge tools read.
"""

__version__ = "0.1.0"
