#!/usr/bin/env python
# coding: utf-8
"""Computing the potential and velocity of Airy wave."""
# Copyright (C) 2017-2019 Matthieu Ancellin
# See LICENSE file at <https://github.com/mancellin/capytaine>

import numpy as np


def airy_waves_potential(points, pb):
    """Compute the potential for Airy waves at a given point (or array of points).

    Parameters
    ----------
    points: array of shape (3) or (N x 3)
        coordinates of the points in which to evaluate the potential.
    pb: DiffractionProblem
        problem with the environmental conditions (g, rho, ...) of interest

    Returns
    -------
    array of shape (1) or (N x 1)
        The potential
    """

    x, y, z = points.T
    k = pb.wavenumber
    h = pb.depth
    wbar = x * np.cos(pb.wave_direction) + y * np.sin(pb.wave_direction)

    if 0 <= k*h < 20:
        cih = np.cosh(k*(z+h))/np.cosh(k*h)
        # sih = np.sinh(k*(z+h))/np.cosh(k*h)
    else:
        cih = np.exp(k*z)
        # sih = np.exp(k*z)

    return -1j*pb.g/pb.omega * cih * np.exp(1j * k * wbar)


def airy_waves_velocity(points, pb):
    """Compute the fluid velocity for Airy waves at a given point (or array of points).

    Parameters
    ----------
    points: array of shape (3) or (N x 3)
        coordinates of the points in which to evaluate the potential.
    pb: DiffractionProblem
        problem with the environmental conditions (g, rho, ...) of interest

    Returns
    -------
    array of shape (3) or (N x 3)
        the velocity vectors
    """

    x, y, z = points.T
    k = pb.wavenumber
    h = pb.depth

    wbar = x * np.cos(pb.wave_direction) + y * np.sin(pb.wave_direction)

    if 0 <= k*h < 20:
        cih = np.cosh(k*(z+h))/np.cosh(k*h)
        sih = np.sinh(k*(z+h))/np.cosh(k*h)
    else:
        cih = np.exp(k*z)
        sih = np.exp(k*z)

    v = pb.g*k/pb.omega * \
        np.exp(1j * k * wbar) * \
        np.array([np.cos(pb.wave_direction) * cih, np.sin(pb.wave_direction) * cih, -1j * sih])

    return v.T


def froude_krylov_force(pb):
    pressure = 1j * pb.omega * pb.rho * airy_waves_potential(pb.body.mesh.faces_centers, pb)
    return pb.body.integrate_pressure(pressure)

