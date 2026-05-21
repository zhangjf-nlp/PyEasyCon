"""
Convergence detection for RNG calibration.

Mathematical model:
  - z_seed   ~ DN(μ_s, σ_s², T_s)      discrete normal, T_s = 15.93
  - z_tv     ~ DN(μ_t, σ_t², 1)        discrete normal, T = 1
  - z_normal ~ DN(μ_n, σ_n², 1)        discrete normal, T = 1, |μ_n| < 157

Observations:
  Seed     = z_seed
  Advances = z_tv * 157 + z_normal

DN (Discrete Normal) PMF:
  P(y=d) = Φ((d + T/2 - μ)/σ) - Φ((d - T/2 - μ)/σ)
  where d = μ + kT, k ∈ Z
"""

import math
from typing import List, Optional, Tuple


T_S = 15.93
ADV_TV_FACTOR = 157

# Default prior sigmas (can be adjusted)
SIGMA_S_DEFAULT = 17.0
SIGMA_T_DEFAULT = 2.0
SIGMA_N_DEFAULT = 20.0


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def dn_pmf(d: float, mu: float, sigma: float, T: float) -> float:
    p = _norm_cdf((d + T / 2 - mu) / sigma) - _norm_cdf((d - T / 2 - mu) / sigma)
    return max(p, 1e-300)


def dn_log_likelihood(mu: float, sigma: float, T: float, observations: List[float]) -> float:
    if sigma <= 0:
        return -float('inf')
    ll = 0.0
    for d in observations:
        ll += math.log(dn_pmf(d, mu, sigma, T))
    return ll


def _grid_search_mu(
    observations: List[float],
    sigma: float,
    T: float,
    center: float,
    search_half_range: float = 50.0,
    step: float = 0.5,
) -> float:
    best_mu = center
    best_ll = -float('inf')
    n_steps = int(search_half_range / step)
    for i in range(-n_steps, n_steps + 1):
        mu = center + i * step
        ll = dn_log_likelihood(mu, sigma, T, observations)
        if ll > best_ll:
            best_ll = ll
            best_mu = mu
    return best_mu


def estimate_mu_s(
    seed_observations: List[float],
    sigma_s: float = SIGMA_S_DEFAULT,
    T_s: float = T_S,
) -> Optional[float]:
    if not seed_observations:
        return None
    center = sorted(seed_observations)[len(seed_observations) // 2]
    coarse = _grid_search_mu(seed_observations, sigma_s, T_s, center, search_half_range=50.0, step=1.0)
    fine = _grid_search_mu(seed_observations, sigma_s, T_s, coarse, search_half_range=2.0, step=0.1)
    return fine


def _decompose_advances(
    adv_observations: List[int],
    mu_n: float,
) -> Tuple[List[int], List[int]]:
    z_tv_list = []
    z_normal_list = []
    for a in adv_observations:
        z_tv = round((a - mu_n) / ADV_TV_FACTOR)
        z_normal = a - z_tv * ADV_TV_FACTOR
        z_tv_list.append(z_tv)
        z_normal_list.append(z_normal)
    return z_tv_list, z_normal_list


def estimate_mu_t_mu_n(
    adv_observations: List[int],
    sigma_t: float = SIGMA_T_DEFAULT,
    sigma_n: float = SIGMA_N_DEFAULT,
    max_iter: int = 20,
) -> Tuple[Optional[float], Optional[float]]:
    if not adv_observations:
        return None, None

    mu_n = 0.0
    for iteration in range(max_iter):
        z_tv_list, z_normal_list = _decompose_advances(adv_observations, mu_n)

        mu_t_new = float(sorted(z_tv_list)[len(z_tv_list) // 2])

        if len(z_normal_list) >= 3:
            mu_n_new = float(sorted(z_normal_list)[len(z_normal_list) // 2])
        else:
            mu_n_new = mu_n

        if abs(mu_n_new - mu_n) < 0.01 and iteration > 0:
            mu_n = mu_n_new
            break
        mu_n = mu_n_new

    return mu_t_new, mu_n


def check_seed_convergence(
    seed_observations: List[float],
    target_seed: float,
    sigma_s: Optional[float] = None,
) -> Tuple[bool, float, Optional[float]]:
    if len(seed_observations) < 2:
        return False, float('inf'), None

    if sigma_s is None:
        mu_s = estimate_mu_s(seed_observations)
        if mu_s is None:
            return False, float('inf'), None
    else:
        mu_s = estimate_mu_s(seed_observations, sigma_s)
        if mu_s is None:
            return False, float('inf'), None

    distance = abs(target_seed - mu_s)
    converged = distance < T_S / 2
    return converged, distance, mu_s


def check_advances_convergence(
    adv_observations: List[int],
    target_adv: int,
    sigma_t: Optional[float] = None,
    sigma_n: Optional[float] = None,
) -> Tuple[bool, bool, float, Optional[float], Optional[float]]:
    if len(adv_observations) < 2:
        return False, False, float('inf'), None, None

    sigma_t = sigma_t or SIGMA_T_DEFAULT
    sigma_n = sigma_n or SIGMA_N_DEFAULT

    mu_t, mu_n = estimate_mu_t_mu_n(adv_observations, sigma_t, sigma_n)
    if mu_t is None or mu_n is None:
        return False, False, float('inf'), None, None

    z_tv_target = round((target_adv - mu_n) / ADV_TV_FACTOR)
    z_n_target = target_adv - z_tv_target * ADV_TV_FACTOR

    z_tv_mode = round(mu_t)
    z_n_mode = round(mu_n)

    tv_ok = z_tv_target == z_tv_mode
    n_ok = z_n_target == z_n_mode

    distance = abs(target_adv - (mu_t * ADV_TV_FACTOR + mu_n))
    return tv_ok, n_ok, distance, mu_t, mu_n


def check_convergence(
    seed_observations: List[float],
    adv_observations: List[int],
    target_seed: float,
    target_adv: int,
    sigma_s: Optional[float] = None,
    sigma_t: Optional[float] = None,
    sigma_n: Optional[float] = None,
) -> Tuple[bool, bool, bool, bool, Optional[float], Optional[float], Optional[float]]:
    seed_ok, seed_dist, mu_s = check_seed_convergence(seed_observations, target_seed, sigma_s)
    tv_ok, n_ok, adv_dist, mu_t, mu_n = check_advances_convergence(adv_observations, target_adv, sigma_t, sigma_n)
    both_ok = sum([seed_ok, tv_ok, n_ok]) >= 2
    return both_ok, seed_ok, tv_ok, n_ok, mu_s, mu_t, mu_n
