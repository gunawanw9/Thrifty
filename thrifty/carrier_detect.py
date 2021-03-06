"""
Detect the presence of a carrier in a block of data.

Essentially checks for the frequency bin with the highest energy and tests it
against the threshold (simple threshold detector).
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import scipy.signal


def fft_range_index(start, stop, length):
    """Convert a range of frequency bins to FFT indices.

    The range [start, stop] is a closed interval.

    Parameters
    ----------
    start : int
    stop : int
    length : int
        FFT length

    Returns
    -------
    start_idx : int
    stop_idx : int
        Note that `stop` may be >= length, in which case `np.take` should be
        used with the `mode=wrap` argument when taking elements from the FFT.

    Examples
    --------
    >>> fft_range_index(50, 100, 1024)
    (50, 100)
    >>> fft_range_index(0, -1, 1024)
    (0, 1023)
    >>> fft_range_index(-10, 10, 1024)
    (1014, 1034)
    >>> fft_range_index(-1, 0, 1024)
    (1023, 1024)
    """
    if abs(start) >= length or abs(stop) >= length:
        raise ValueError("Frequency window out of range: {} - {}"
                         .format(start, stop))
    if start < 0 and stop >= 0:
        start, stop = length+start, length+stop
    if start < 0:
        start = length+start
    if stop < 0:
        stop = length+stop
    if stop < start:
        start, stop = stop, start
    return start, stop


def detect(fft_mag, thresh_coeffs, window=None, peak_filter=None):
    """Detect the presence of a carrier in a FFT.

    Parameters
    ----------
    fft_mag : :class:`numpy.ndarray`
        Magnitude of FFT.
    thresh_coeffs : (float, float, float) tuple
        Coefficients of threshold formula: (constant, snr, stddev).
    window : (int, int) tuple
        Limit detection to the frequency bins [start, stop].
    peak_filter : :class:`numpy.ndarray`
        Coefficients of FIR filter (weights) applied to window in order to
        match the shape of the peak for a better estimate of the peak's energy.
        The window is effectively correlated with the peak_filter array. The
        weights should be normalized such that sum(weights**2) = 1. It is
        assumed that the peak is located at the largest coefficient. Note that
        `window` should compensate for the decreased window size.

    Returns
    -------
    detected : bool
        Detection verdict.
    peak_idx : int
        Estimated position of carrier in FFT.
    peak_mag : float
        Estimated peak magnitude.
    noise_rms : float
        Estimated noise rms.
    """

    peak_idx, peak_mag = _window_peak(fft_mag, window, peak_filter)
    noise_rms = _estimate_noise(fft_mag, peak_mag)
    threshold = _calculate_threshold(fft_mag, thresh_coeffs, noise_rms)
    detected = (peak_mag > threshold)
    return detected, peak_idx, peak_mag, noise_rms


def _estimate_noise(fft_mag, peak_mag):
    fft_energy = np.sum(fft_mag**2)
    # The energy in the wide-band positioning signal and the narrow-band
    # unmodulated carrier is about equal for OOK modulation and a pseudo-random
    # code. Subtract two times the peak power to compensate for both the
    # correlation peak's energy and the energy of the unmodulated carrier.
    peak_power = peak_mag**2
    noise_power = (fft_energy - 2*peak_power) / (len(fft_mag) - 1)
    return np.sqrt(noise_power)


def _calculate_threshold(fft_mag, thresh_coeffs, noise_rms):
    thresh_const, thresh_snr, thresh_stddev = thresh_coeffs
    stddev = np.std(fft_mag) if thresh_stddev else 0
    thresh = (thresh_const + thresh_snr * noise_rms**2
              + thresh_stddev * stddev**2)
    return np.sqrt(thresh)


def _get_window(array, window):
    if window is None:
        start, stop = 0, -1
    else:
        start, stop = window
    start_idx, stop_idx = fft_range_index(start, stop, len(array))
    selection = np.take(array, range(start_idx, stop_idx+1), mode='wrap')
    return selection, start_idx


def _filter(fft_mag, weights):
    """Apply the filter represented by the given weights.
    The weights should be normalized such that the total energy of the
    coefficients is unity, thus sum(weights**2) = 1."""
    delay = len(weights) - np.argmax(weights) - 1
    coeffs = weights[::-1]**2
    filtered = np.sqrt(scipy.signal.lfilter(coeffs, 1, fft_mag**2))
    return filtered, delay


def _window_peak(fft_mag, window, peak_filter):
    mags, start_idx = _get_window(fft_mag, window)

    if peak_filter is not None:
        mags, filter_delay = _filter(mags, peak_filter)
    else:
        filter_delay = 0

    max_idx = np.argmax(mags)
    peak_mag = mags[max_idx]

    peak_idx = max_idx - filter_delay
    peak_idx += start_idx
    if peak_idx > len(fft_mag):
        peak_idx -= len(fft_mag)

    return peak_idx, peak_mag
