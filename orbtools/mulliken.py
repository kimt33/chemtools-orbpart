"""Mulliken population analysis."""
import numpy as np
from orbtools.orthogonalization import power_symmetric
from orbtools.quasi import project


# FIXME: bad name (since providing atom_weights will result in the population not being Mulliken)
def mulliken_populations(
    coeff_ab_mo, occupations, olp_ab_ab, num_atoms, ab_atom_indices, atom_weights=None
):
    r"""Return the Mulliken populations of the given molecular orbitals.

    ..math::

        \ket{\psi_i} = \sum_j \ket{\phi_j} C_{ji}

    where :math:`\psi_i` is a molecular orbital and :math:`\phi_j` is an atomic orbital.

    ..math::

        1 &= \braket{\psi_i | \psi_i}\\
        N &= \sum_i^{occ} n_i \braket{\psi_i | \psi_i}\\

    where :math:`N` is the number of electrons and :math:`n_i` is the occupation number of molecular
    orbital :math:`\psi_i`.

    ..math::

        N &= \sum_i^{occ} n_i \braket{\psi_i | \psi_i}\\
        &= \sum_i^{occ} n_i \sum_{jk} C_{ij}^\dagger \braket{\phi_j | \phi_k} C_{ki}\\
        &= \sum_{jk} \braket{\phi_j | \phi_k} \sum_i^{occ} C_{ki} n_i C_{ij}^\dagger\\
        &= \sum_{jk} S_{jk} X_{kj}\\

    where

    ..math::

        S_{jk} = \braket{\phi_j | \phi_k}

    is the overlap of the atomic orbitals and

    ..math::

        P_{kj} = \sum_i^{occ} C_{ki} n_i C_{ij}^\dagger

    is the density matrix (or charge-density bond order matrix).

    We can now divide up the total number of electrons into corresponding contribution from each
    atom

    ..math::

        N = \sum_A \sum_{jk} w_{jk}^A S_{jk} P_{kj}

    where :math:`w_{jk}^A` corresponds weight for the electrons associated with atomic orbitals
    :math:`\phi_j` and :math:`\phi_k` belonging to atom A. Different values of :math:`w_{jk}^A`
    correspond to different partitioning schemes.

    Note that the weights must be normalized. i.e. :math:`\sum_A w_{jk}^A = 1` for all :math:`j` and
    :math:`k` such that

    ..math::

        N &= \sum_A \sum_{jk} w_{jk}^A S_{jk} P_{kj}\\
        &= \sum_{jk} (\sum_A w_{jk}^A) S_{jk} P_{kj}\\
        &= \sum_{jk} S_{jk} P_{kj}

    Parameters
    ----------
    coeff_ab_mo : np.ndarray(K, M)
        Transformation matrix from the atomic basis to molecular orbitals.
        Rows correspond to the atomic basis.
        Columns correspond to the molecular orbitals.
        The transformation matrix is applied to the right:
        .. math::

            \ket{\psi_i} = \sum_j \phi_i C_{ij}

        Data type must be float.
        `K` is the number of atomic orbitals and `M` is the number of molecular orbitals.
    occupations : np.ndarray(M,)
        Occupation numbers of each molecular orbital.
        Data type must be integers or floats.
        `M` is the number of molecular orbitals.
    olp_ab_ab : np.ndarray(K, K)
        Overlap between atomic basis functions.
        Data type must be floats.
        `K` is the number of atomic orbitals.
    num_atoms : int
        Number of atoms.
        Must be an integer.
    ab_atom_indices : np.ndarray(K,)
        Index of the atom to which each atomic basis function belongs.
        Data type must be integers.
        `K` is the number of atomic orbitals.
    atom_weights : np.ndarray(A, K, K)
        Weights of the atomic orbital pairs for the atoms. In other words, this weight controls the
        amount of electrons associated with an atomic orbital pair that will be attributed to an
        atom.
        `A` is the number of atoms and `K` is the number of atomic orbitals.
        Default is the Mulliken partitioning scheme where two orbitals that belong to the given atom
        is 1, only one orbital that belong to the given atoms is 0.5, and no orbitals is 0.

    Returns
    -------
    population : np.ndarray(M,)
        Number of electrons associated with each atom.
        `M` is the number of atoms, which will be assumed to be the maximum index in
        `ab_atom_indices`.

    Raises
    ------
    TypeError
        If `coeff_ab_mo` is not a two-dimensional numpy array of floats.
        If `occupations` is not a one-dimensional numpy array of ints/floats.
        If `olp_ab_ab` is not a two-dimensional numpy array of floats.
        If `num_atoms` is not an integer.
        If `ab_atom_indices` is not a a one-dimensional numpy array of ints.
        If `atom_weights` is not the default value (`None`) and is not a 3-dimensional numpy array
        of ints/flotas.
    ValueError
        If `olp_ab_ab` is not square.
        If the number of rows in `coeff_ab_mo` is not equal to the number of rows in
        `olp_ab_ab`.
        If the number of columns in `coeff_ab_mo` is not equal to the number of entries in
        `occupations`.
        If `olp_ab_ab` is not symmetric.
        If `olp_ab_ab` does not have diagonals of 1.
        If molecular orbitals are not normalized.
        If `occupations` has any negative numbers.
        If `ab_atom_indices` does not have the same number of entries as there are atomic basis
        functions (i.e. number of rows in `olp_ab_ab`).
        If `ab_atom_indices` contains indices that are less than 0 or greater than or equal to the
        number of atoms.
        If `atom_weights` has first dimension that is not equal to the number of atoms.
        If `atom_weights` has second and third dimensions that are not equal to the number of atomic
        orbitals.
        If `atom_weights` is not symmetric with respect to the interchange of the second and third
        indices.
        If `atom_weights` is not normalized. i.e. sum over the first dimension does not result in
        1's.

    Warns
    -----
    If there are any occupation numbers of the molecular orbitals that is greater than 2.
    If the total population does not match the sum of the electrons provided by the `occupations`.

    """
    # pylint: disable=R0912,R0915
    if not (
        isinstance(coeff_ab_mo, np.ndarray) and coeff_ab_mo.ndim == 2 and coeff_ab_mo.dtype == float
    ):
        raise TypeError(
            "Transformation matrix from atomic basis functions to molecular orbitals must be a "
            "two-dimensional numpy array of floats."
        )
    if not (
        isinstance(occupations, np.ndarray)
        and occupations.ndim == 1
        and occupations.dtype in [float, int]
    ):
        raise TypeError(
            "Molecular orbital occupation numbers must be not a one-dimensional numpy array of "
            "floats or ints."
        )
    if not (isinstance(olp_ab_ab, np.ndarray) and olp_ab_ab.ndim == 2 and olp_ab_ab.dtype == float):
        raise TypeError(
            "Overlap of the atomic basis functions must be a two-dimensional numpy array of floats."
        )
    if not isinstance(num_atoms, int):
        raise TypeError("Number of atoms must be an integer.")
    if not (
        isinstance(ab_atom_indices, np.ndarray)
        and ab_atom_indices.ndim == 1
        and ab_atom_indices.dtype == int
    ):
        raise TypeError(
            "Atom indices of each atomic basis function must be a one-dimensional numpy array of "
            "integers with size equal to the number of atomic basis functions."
        )

    if not olp_ab_ab.shape[0] == olp_ab_ab.shape[1]:
        raise ValueError("Overlap matrix is not square.")
    if not coeff_ab_mo.shape[0] == olp_ab_ab.shape[0]:
        raise ValueError(
            "Number of atomic orbitals in the transformation matrix and overlap matrix are not "
            "equal."
        )
    if not coeff_ab_mo.shape[1] == occupations.size:
        raise ValueError(
            "Number of molecular orbitals in the transformation matrix and occupations are not "
            "equal."
        )

    if not np.allclose(olp_ab_ab, olp_ab_ab.T):
        raise ValueError("Overlap of the atomic basis functions must be symmetric.")
    if not np.allclose(np.diag(olp_ab_ab), 1):
        raise ValueError("Overlap of the atomic basis functions must be normalized.")
    if not np.allclose(np.diag(coeff_ab_mo.T.dot(olp_ab_ab).dot(coeff_ab_mo)), 1):
        raise ValueError(
            "Molecular orbitals (and the corresponding transformation matrix) must be normalized."
        )

    if not np.all(occupations >= 0):
        raise ValueError("Occupation numbers must be greater than or equal to 0.")
    if np.any(occupations > 2):
        print("WARNING: Atleast one occupation number exceeds 2.")

    # Check basis mapping
    if ab_atom_indices.size != olp_ab_ab.shape[0]:
        raise ValueError(
            "Number of indices in `ab_atom_indices` must be equal to the number of atomic basis "
            "functions."
        )
    if not (np.all(ab_atom_indices >= 0) and np.all(ab_atom_indices < num_atoms)):
        raise ValueError(
            "Atom indices of each atomic basis function must be greater than or equal to zero and "
            " less than the number of atoms"
        )

    if atom_weights is None:
        num_ab = olp_ab_ab.shape[0]
        # NOTE: creating this numpy array is quite memory intensive. Since nothing here will ever be
        # a computational bottleneck, it will be smarter to use a for loop incorporating the next
        # two parts (weights and density) together. However, we keep these two parts separated to
        # make it easier to implement different weight paradigms.
        atom_weights = np.zeros((num_atoms, num_ab, num_ab))
        ab_atom_indices_separated = ab_atom_indices[None, :] == np.arange(num_atoms)[:, None]
        atom_weights += (ab_atom_indices_separated.astype(float) * 0.5)[:, :, None]
        atom_weights += (ab_atom_indices_separated.astype(float) * 0.5)[:, None, :]
        # code above is equivalent to the following:
        # atom_weights = {}
        # for i in range(num_atoms):
        #     weights = np.zeros(num_ab)
        #     weights[ab_atom_indices == i] = 0.5
        #     atom_weights[i] = weights[:, None] + weights[None, :]
    else:
        if not (
            isinstance(atom_weights, np.ndarray)
            and atom_weights.ndim == 3
            and atom_weights.dtype in [float, int]
        ):
            raise TypeError(
                "Orbital weights for the atoms must be a 3-dimensional numpy array of ints/floats."
            )
        if atom_weights.shape[0] != num_atoms:
            raise ValueError(
                "First dimension of the orbital weights for the atoms must be equal to the number "
                "of atoms."
            )
        if atom_weights.shape[1:] != olp_ab_ab.shape:
            raise ValueError(
                "Second and third dimension of the orbital weights for the atoms must be equal to "
                "the number of atomic orbitals."
            )
        if not np.allclose(atom_weights, np.swapaxes(atom_weights, 1, 2)):
            raise ValueError(
                "Orbital weights for each atom must be symmetric, i.e. `atom_weights` must be "
                "symmetric with respect to the interchange of the second and third indices."
            )
        if not np.allclose(np.sum(atom_weights, axis=0), 1):
            raise ValueError(
                "Orbital weights for the atoms must be normalized, i.e. sum over the first "
                "dimension must result in 1's."
            )

    # NOTE: the axis keyword used here for np.sum uses API introduced in numpy 1.7.0. This means
    # that this function call will restrict the version of numpy used by this package.
    density = (coeff_ab_mo * occupations[None, :]).dot(coeff_ab_mo.T)
    raw_pops = (olp_ab_ab * density.T)[None, :, :] * atom_weights
    output = np.sum(raw_pops, axis=(1, 2))
    # code above is equivalent to the following:
    # output = np.zeros(num_atoms)
    # for atom_ind, weights in atom_weights.items():
    #     output[atom_ind] = np.sum(olp_ab_ab * density.T * weights)

    if not abs(np.sum(occupations) - np.sum(output)) < 1e-6:
        print("WARNING: Population does not match up with the number of electrons.")

    return output


def mulliken_populations_newbasis(
    coeff_ab_mo,
    occupations,
    olp_ab_ab,
    num_atoms,
    coeff_ab_new,
    new_atom_indices,
    new_atom_weights=None,
):
    r"""Return the Mulliken populations of the given system in a new basis set.

    Parameters
    ----------
    coeff_ab_mo : np.ndarray(K, M)
        Transformation matrix from the atomic basis to molecular orbitals.
        Rows correspond to the atomic basis.
        Columns correspond to the molecular orbitals.
        The transformation matrix is applied to the right:
        .. math::

            \ket{\psi_i} = \sum_j \phi_i C_{ij}

        Data type must be float.
        `K` is the number of atomic orbitals and `M` is the number of molecular orbitals.
    occupations : np.ndarray(M,)
        Occupation numbers of each molecular orbital.
        Data type must be integers or floats.
        `M` is the number of molecular orbitals.
    olp_ab_ab : np.ndarray(K, K)
        Overlap between atomic basis functions.
        Data type must be floats.
        `K` is the number of atomic orbitals.
    num_atoms : int
        Number of atoms.
        Must be an integer.
    coeff_ab_new : np.ndarray(K, L)
        Transformation matrix from the atomic basis to new basis functions.
        Rows correspond to the atomic basis.
        Columns correspond to the new basis functions.
        The transformation matrix is applied to the right.
        Data type must be float.
        `K` is the number of atomic orbitals and `L` is the number of new basis functions.
    new_atom_indices : np.ndarray(L,)
        Index of the atom to which each of the new basis function belongs.
        Data type must be integers.
        `L` is the number of atomic orbitals.
    new_atom_weights : np.ndarray(A, L, L)
        Weights of the pair of new basis functions for the atoms. In other words, this weight
        controls the amount of electrons associated with an new basis function pair that will be
        attributed to an atom.
        `A` is the number of atoms and `K` is the number of new basis functions.
        Default is the Mulliken partitioning scheme where two basis functions that belong to the
        given atom is 1, only one basis function that belong to the given atoms is 0.5, and no basis
        functions is 0.

    Returns
    -------
    population : np.ndarray(M,)
        Number of electrons associated with each atom.
        `M` is the number of atoms, which will be assumed to be the maximum index in
        `ab_atom_indices`.

    See Also
    --------
    orbtools.mulliken.mulliken_populations

    """
    olp_new_new = coeff_ab_new.T.dot(olp_ab_ab).dot(coeff_ab_new)
    olp_new_mo = coeff_ab_new.T.dot(olp_ab_ab).dot(coeff_ab_mo)
    coeff_new_mo = project(olp_new_new, olp_new_mo)
    return mulliken_populations(
        coeff_new_mo,
        occupations,
        olp_new_new,
        num_atoms,
        new_atom_indices,
        atom_weights=new_atom_weights,
    )


def lowdin_populations(
    coeff_ab_mo, occupations, olp_ab_ab, num_atoms, ab_atom_indices, atom_weights=None
):
    r"""Return the Lowdin populations of the given molecular orbitals in atomic orbital basis set.

    Lowdin population analysis is simply the Mulliken population analysis where the basis functions
    are symmeterically orthogonalized.

    Parameters
    ----------
    coeff_ab_mo : np.ndarray(K, M)
        Transformation matrix from the atomic basis to molecular orbitals.
        Rows correspond to the atomic basis.
        Columns correspond to the molecular orbitals.
        The transformation matrix is applied to the right:
        .. math::

            \ket{\psi_i} = \sum_j \phi_i C_{ij}

        Data type must be float.
        `K` is the number of atomic orbitals and `M` is the number of molecular orbitals.
    occupations : np.ndarray(M,)
        Occupation numbers of each molecular orbital.
        Data type must be integers or floats.
        `M` is the number of molecular orbitals.
    olp_ab_ab : np.ndarray(K, K)
        Overlap between atomic basis functions.
        Data type must be floats.
        `K` is the number of atomic orbitals.
    num_atoms : int
        Number of atoms.
        Must be an integer.
    ab_atom_indices : np.ndarray(K,)
        Index of the atom to which each atomic basis function belongs.
        Data type must be integers.
        `K` is the number of atomic orbitals.
    atom_weights : np.ndarray(A, K, K)
        Weights of the atomic orbital pairs for the atoms. In other words, this weight controls the
        amount of electrons associated with an atomic orbital pair that will be attributed to an
        atom.
        `A` is the number of atoms and `K` is the number of atomic orbitals.
        Default is the Mulliken partitioning scheme where two orbitals that belong to the given atom
        is 1, only one orbital that belong to the given atoms is 0.5, and no orbitals is 0.

    Returns
    -------
    population : np.ndarray(M,)
        Number of electrons associated with each atom.
        `M` is the number of atoms, which will be assumed to be the maximum index in
        `ab_atom_indices`.

    """
    coeff_ab_oab = power_symmetric(olp_ab_ab, -0.5)
    return mulliken_populations_newbasis(
        coeff_ab_mo,
        occupations,
        olp_ab_ab,
        num_atoms,
        coeff_ab_oab,
        ab_atom_indices,
        new_atom_weights=atom_weights,
    )
