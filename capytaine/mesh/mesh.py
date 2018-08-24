#!/usr/bin/env python
# coding: utf-8
"""
This module concerns mesh data structures.

Based on Meshmagick by Francois Rongere (EC Nantes).
"""

import logging
from itertools import count

import numpy as np

from capytaine.mesh.mesh_properties import compute_faces_properties, connectivity
from capytaine.mesh.mesh_quality import (merge_duplicates, heal_normals, remove_unused_vertices,
                                         heal_triangles, remove_degenerated_faces)
from capytaine.tools.geometry import Abstract3DObject, Plane, inplace_or_not

LOG = logging.getLogger(__name__)


class Mesh(Abstract3DObject):
    """A class to handle unstructured meshes.

    Parameters
    ----------
    vertices : array_like of shape (nv, 3)
        Array of mesh vertices coordinates. Each line of the array represents one vertex
        coordinates
    faces : array_like of shape (nf, 4)
        Arrays of mesh connectivities for faces. Each line of the array represents indices of
        vertices that form the face, expressed in counterclockwise order to ensure outward normals
        description.
    name : str, optional
        The mesh's name. If None, mesh is given an automatic name based on its internal ID.
    """
    _ids = count(0)

    def __init__(self, vertices=None, faces=None, name=None):

        if vertices is None:
            vertices = np.zeros((0, 3))

        if faces is None:
            faces = np.zeros((0, 4))

        if name is None:
            self.name = f'mesh_{next(Mesh._ids)}'
        else:
            self.name = str(name)

        assert all(int(vertex_id) == vertex_id >= 0 for face in faces for vertex_id in face), \
            "Faces of a mesh should be provided as positive integers (ids of vertices)"

        self._vertices = np.array(vertices, dtype=np.float)
        self._faces = np.array(faces, dtype=np.int)

        assert self._vertices.shape[1] == 3, \
            "Vertices of a mesh should be provided as a sequence of 3-ple."
        assert self._faces.shape[1] == 4, \
            "Faces of a mesh should be provided as a sequence of 4-ple."
        assert len(self._faces) == 0 or self._faces.max()+1 <= len(self._vertices), \
            "The array of faces references vertices that are not in the mesh."

        self.__internals__ = dict()

    def __str__(self):
        return (f"{self.__class__.__name__}(nb_vertices={self.nb_vertices}, "
                f"nb_faces={self.nb_faces}, name={self.name})")

    @property
    def nb_vertices(self) -> int:
        """Get the number of vertices in the mesh."""
        return self._vertices.shape[0]

    @property
    def vertices(self) -> np.ndarray:
        """Get the vertices array coordinate of the mesh."""
        return self._vertices

    @vertices.setter
    def vertices(self, value) -> None:
        self._vertices = np.asarray(value, dtype=np.float).copy()
        self.__internals__.clear()
        return

    @property
    def nb_faces(self) -> int:
        """Get the number of faces in the mesh."""
        return self._faces.shape[0]

    @property
    def faces(self) -> np.ndarray:
        """Get the faces connectivity array of the mesh."""
        return self._faces

    @faces.setter
    def faces(self, value):
        self._faces = np.asarray(value, dtype=np.int).copy()
        self.__internals__.clear()
        return

    def copy(self, name=None) -> 'Mesh':
        """Get a copy of the current mesh instance.

        Parameters
        ----------
        name : string, optional
            a name for the new mesh

        Returns
        -------
        Mesh
            mesh instance copy
        """
        from copy import deepcopy
        new_mesh = deepcopy(self)
        if name is not None:
            new_mesh.name = name
        return new_mesh

    def merge(self):
        """Dummy method to be generalized for collections of meshes."""
        return self

    def tree_view(self, **kwargs):
        """Dummy method to be generalized for collections of meshes."""
        return self.name

    def to_meshmagick(self):
        """Convert the Mesh object as a Mesh object from meshmagick.
        Mostly for debugging."""
        from meshmagick.mesh import Mesh
        return Mesh(self.vertices, self.faces, name=self.name)

    ##################
    #  Extract face  #
    ##################

    def get_face(self, face_id):
        """Get the face described by its vertices connectivity.

        Parameters
        ----------
        face_id : int
            Face id

        Returns
        -------
        ndarray
            If the face is a triangle, the array has 3 components, else it has 4 (quadrangle)
        """
        if self.is_triangle(face_id):
            return self._faces[face_id, :3]
        else:
            return self._faces[face_id]

    def extract_faces(self, id_faces_to_extract, return_index=False):
        """
        Extracts a new mesh from a selection of faces ids

        Parameters
        ----------
        id_faces_to_extract : ndarray
            Indices of faces that have to be extracted
        return_index: bool
            Flag to output old indices

        Returns
        -------
        Mesh
            A new Mesh instance composed of the extracted faces
        """
        nv = self.nb_vertices

        # Determination of the vertices to keep
        vertices_mask = np.zeros(nv, dtype=bool)
        vertices_mask[self._faces[id_faces_to_extract].flatten()] = True
        id_v = np.arange(nv)[vertices_mask]

        # Building up the vertex array
        v_extracted = self._vertices[id_v]
        new_id__v = np.arange(nv)
        new_id__v[id_v] = np.arange(len(id_v))

        faces_extracted = self._faces[id_faces_to_extract]
        faces_extracted = new_id__v[faces_extracted.flatten()].reshape((len(id_faces_to_extract), 4))

        extracted_mesh = Mesh(v_extracted, faces_extracted)

        extracted_mesh.name = 'mesh_extracted_from_%s' % self.name

        if return_index:
            return extracted_mesh, id_v
        else:
            return extracted_mesh

    ######################
    #  Faces properties  #
    ######################

    def _has_faces_properties(self):
        return 'faces_areas' in self.__internals__

    def _remove_faces_properties(self):
        if self._has_faces_properties():
            del self.__internals__['faces_areas']
            del self.__internals__['faces_centers']
            del self.__internals__['faces_normals']
            del self.__internals__['faces_radiuses']
        return

    @property
    def faces_areas(self):
        """Get the array of faces areas of the mesh

        Returns
        -------
        ndarray
        """
        if 'faces_areas' not in self.__internals__:
            self.__internals__.update(compute_faces_properties(self))
        return self.__internals__['faces_areas']

    @property
    def faces_centers(self):
        """Get the array of faces centers of the mesh

        Returns
        -------
        ndarray
        """
        if 'faces_centers' not in self.__internals__:
            self.__internals__.update(compute_faces_properties(self))
        return self.__internals__['faces_centers']

    @property
    def faces_normals(self):
        """Get the array of faces normals of the mesh

        Returns
        -------
        ndarray
        """
        if 'faces_normals' not in self.__internals__:
            self.__internals__.update(compute_faces_properties(self))
        return self.__internals__['faces_normals']

    @property
    def faces_radiuses(self):
        """Get the array of faces radiuses of the mesh.

        Returns
        -------
        ndarray
        """
        if 'faces_radiuses' not in self.__internals__:
            self.__internals__.update(compute_faces_properties(self))
        return self.__internals__['faces_radiuses']

    ###############################
    #  Triangles and quadrangles  #
    ###############################

    def is_triangle(self, face_id):
        """Returns if a face is a triangle

        Parameters
        ----------
        face_id : int
            Face id

        Returns
        -------
        bool
            True if the face with id face_id is a triangle
        """
        assert 0 <= face_id < self.nb_faces
        return self._faces[face_id, 0] == self._faces[face_id, -1]

    def _triangles_quadrangles(self):
        triangle_mask = (self._faces[:, 0] == self._faces[:, -1])
        quadrangles_mask = np.invert(triangle_mask)
        triangles_quadrangles = {'triangles_ids': np.where(triangle_mask)[0],
                                 'quadrangles_ids': np.where(quadrangles_mask)[0]}
        self.__internals__.update(triangles_quadrangles)
        return

    def _has_triangles_quadrangles(self):
        return 'triangles_ids' in self.__internals__

    def _remove_triangles_quadrangles(self):
        if 'triangles_ids' in self.__internals__:
            del self.__internals__['triangles_ids']
            del self.__internals__['quadrangles_ids']
        return

    @property
    def triangles_ids(self):
        """Get the array of ids of triangle shaped faces

        Returns
        -------
        ndarray
        """
        if 'triangles_ids' not in self.__internals__:
            self._triangles_quadrangles()
        return self.__internals__['triangles_ids']

    @property
    def nb_triangles(self):
        """Get the number of triangles in the mesh

        Returns
        -------
        int
        """
        if 'triangles_ids'not in self.__internals__:
            self._triangles_quadrangles()
        return len(self.__internals__['triangles_ids'])

    @property
    def quadrangles_ids(self):
        """Get the array of ids of quadrangle shaped faces

        Returns
        -------
        ndarray
        """
        if 'triangles_ids' not in self.__internals__:
            self._triangles_quadrangles()
        return self.__internals__['quadrangles_ids']

    @property
    def nb_quadrangles(self):
        """Get the number of quadrangles in the mesh

        Returns
        -------
        int
        """
        if 'triangles_ids' not in self.__internals__:
            self._triangles_quadrangles()
        return len(self.__internals__['quadrangles_ids'])

    #############
    #  Display  #
    #############

    @property
    def axis_aligned_bbox(self):
        """Get the axis aligned bounding box of the mesh.

        Returns
        -------
        tuple
            (xmin, xmax, ymin, ymax, zmin, zmax)
        """
        if self.nb_vertices > 0:
            x, y, z = self._vertices.T
            return (x.min(), x.max(),
                    y.min(), y.max(),
                    z.min(), z.max())
        else:
            return tuple(np.zeros(6))

    @property
    def squared_axis_aligned_bbox(self):
        """Get a squared axis aligned bounding box of the mesh.

        Returns
        -------
        tuple
            (xmin, xmax, ymin, ymax, zmin, zmax)

        Note
        ----
        This method differs from `axis_aligned_bbox()` by the fact that the bounding box that is returned is squared but have the same center as the AABB
        """
        xmin, xmax, ymin, ymax, zmin, zmax = self.axis_aligned_bbox
        (x0, y0, z0) = np.array([xmin+xmax, ymin+ymax, zmin+zmax]) * 0.5
        d = (np.array([xmax-xmin, ymax-ymin, zmax-zmin]) * 0.5).max()

        return x0-d, x0+d, y0-d, y0+d, z0-d, z0+d

    def show(self, **kwargs):
        self.show_vtk(**kwargs)

    def show_vtk(self):
        """Shows the mesh in the meshmagick viewer"""
        from capytaine.ui.vtk.MMviewer import compute_vtk_polydata, MMViewer

        vtk_polydata = compute_vtk_polydata(self)
        self.viewer = MMViewer()
        self.viewer.add_polydata(vtk_polydata)
        self.viewer.show()
        self.viewer.finalize()

    def show_matplotlib(self, ax=None,
                        normal_vectors=False, scale_normal_vector=None,
                        saveas=None,
                        **kwargs):
        """Poor man's viewer with matplotlib.

        Parameters
        ----------
        ax: matplotlib axis
            The 3d axis in which to plot the mesh. If not provided, create a new one.
        normal_vector: bool
            If True, print normal vector.
        scale_normal_vector: array of shape (nb_faces, )
            Scale separately each of the normal vectors.
        saveas: str
            file path where to save the image

        Other parameters are passed to Poly3DCollection.
        """
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        default_axis = ax is None
        if default_axis:
            fig = plt.figure()
            ax = fig.add_subplot(111, projection="3d")

        faces = []
        for face in self.faces:
            vertices = []
            for index_vertex in face:
                vertices.append(self.vertices[int(index_vertex), :])
            faces.append(vertices)
        if 'facecolors' not in kwargs:
            kwargs['facecolors'] = (0.3, 0.3, 0.3, 0.3)
        if 'edgecolor' not in kwargs:
            kwargs['edgecolor'] = 'k'
        ax.add_collection3d(Poly3DCollection(faces, **kwargs))

        # Plot normal vectors.
        if normal_vectors:
            if scale_normal_vector is not None:
                vectors = (scale_normal_vector * self.faces_normals.T).T
            else:
                vectors = self.faces_normals
            ax.quiver(*zip(*self.faces_centers), *zip(*vectors), length=0.2)

        if default_axis:
            ax.set_xlabel("x")
            ax.set_ylabel("y")

            xmin, xmax, ymin, ymax, zmin, zmax = self.squared_axis_aligned_bbox
            ax.set_xlim(xmin, xmax)
            ax.set_ylim(ymin, ymax)
            ax.set_zlim(zmin, zmax)

            if saveas is not None:
                plt.tight_layout()
                plt.savefig(saveas)
            else:
                plt.show()

    ################################
    #  Transformation of the mesh  #
    ################################

    @inplace_or_not
    def translate(self, vector):
        """Translates the mesh in 3D giving the 3 distances along coordinate axes.

        Parameters
        ----------
        vector : array_like
            translation vector

        Return
        ------
        Mesh
        """
        vector = np.asarray(vector, dtype=np.float)
        assert vector.shape == (3,), "The translation vector should be given as a 3-ple of values."

        self.vertices += vector

        # Updating properties if any
        if self._has_faces_properties():
            self.__internals__['faces_centers'] += vector

        if self.has_surface_integrals():
            self._remove_surface_integrals()

        return self

    @inplace_or_not
    def rotate(self, axis, angle):
        """Rotate the mesh of a given angle around an axis.

        Parameters
        ----------
        axis : Axis
        angle : float

        Return
        ------
        Mesh
        """
        rot_matrix = axis.rotation_matrix(angle)

        self._vertices = np.transpose(np.dot(rot_matrix, self._vertices.T))

        # Updating faces properties if any
        if self._has_faces_properties():
            normals = self.__internals__['faces_normals']
            centers = self.__internals__['faces_centers']
            self.__internals__['faces_normals'] = np.transpose(np.dot(rot_matrix, normals.T))
            self.__internals__['faces_centers'] = np.transpose(np.dot(rot_matrix, centers.T))

        if self.has_surface_integrals():
            self._remove_surface_integrals()

        return self

    # OTHER
    @inplace_or_not
    def flip_normals(self):
        """Flips every normals of the mesh."""

        self._faces = np.fliplr(self._faces)

        if self._has_faces_properties():
            self.__internals__['faces_normals'] *= -1

        if self.has_surface_integrals():
            self._remove_surface_integrals()

        return self

    @inplace_or_not
    def mirror(self, plane):
        """Mirrors the mesh instance with respect to a plane.

        Parameters
        ----------
        plane : Plane
            The mirroring plane
        """
        self.vertices -= 2 * np.outer(np.dot(self.vertices, plane.normal) - plane.c, plane.normal)
        self.flip_normals()
        self.__internals__.clear()
        return self

    def get_immersed_part(self, free_surface=0.0, sea_bottom=-np.infty):
        """Clip the mesh with two horizontal planes."""
        from capytaine.mesh.mesh_clipper import MeshClipper
        if self.vertices[:, 2].min() > free_surface or self.vertices[:, 2].max() < sea_bottom:
            return None  # The mesh has no wet faces.

        elif self.vertices[:, 2].min() > sea_bottom and self.vertices[:, 2].max() < free_surface:
            return self.copy(name=f"{self.name}_clipped")  # The mesh is completely immersed. Non need for clipping.

        else:
            clipped_mesh = MeshClipper(self,
                                       plane=Plane(normal=(0.0, 0.0, 1.0),
                                                   scalar=free_surface)).clipped_mesh

            if sea_bottom > -np.infty:
                clipped_mesh = MeshClipper(clipped_mesh,
                                           plane=Plane(normal=(0.0, 0.0, -1.0),
                                                       scalar=-sea_bottom)).clipped_mesh

            clipped_mesh.remove_unused_vertices()
            clipped_mesh.name = f"{self.name}_clipped"
            return clipped_mesh

    def triangulate_quadrangles(self):
        """Triangulates every quadrangles of the mesh by simple spliting.

        Each quadrangle gives two triangles.

        Note
        ----
        No checking is made on the triangle quality is done.
        """
        # TODO: Ensure the best quality aspect ratio of generated triangles

        # Defining both triangles id lists to be generated from quadrangles
        t1 = (0, 1, 2)
        t2 = (0, 2, 3)

        faces = self._faces

        # Triangulation
        new_faces = faces[self.quadrangles_ids].copy()
        new_faces[:, :3] = new_faces[:, t1]
        new_faces[:, -1] = new_faces[:, 0]

        faces[self.quadrangles_ids, :3] = faces[:, t2][self.quadrangles_ids]
        faces[self.quadrangles_ids, -1] = faces[self.quadrangles_ids, 0]

        faces = np.concatenate((faces, new_faces))

        LOG.info('\nTriangulating quadrangles')
        if self.nb_quadrangles != 0:
            LOG.info('\t-->{:d} quadrangles have been split in triangles'.format(self.nb_quadrangles))

        self.__internals__.clear()

        self._faces = faces

        return faces

    ####################
    #  Combine meshes  #
    ####################

    def join_meshes(*meshes, name=None):
        from capytaine.mesh.meshes_collection import CollectionOfMeshes
        return CollectionOfMeshes(meshes, name=name).merge()

    def __add__(self, mesh_to_add):
        return self.join_meshes(mesh_to_add)

    ####################
    #  Compare meshes  #
    ####################
    # The objective is to write a mesh as a set of faces in order to check for equality or to
    # compute differences of meshes. Each face can be represented as a 4x3 array (4 triplets of
    # coordinates).
    # However, it is tricky on several aspects:
    #   * The builtin set class compares the hashes of its objects. Since numpy ndarray are not
    #   hashable, the 4x3 array can be transformed into a tuple of tuples (which is hashable).
    #   * Two faces with different numbering of the faces (but the same ordering) are recorded as
    #   different.
    #   * Two vertices equal up to machine precision can be recorded as different, due to rounding
    #   errors.
    #
    # A possible solution is to define a Face class and a Vertex class with the appropriate __eq__
    # and __hash__.
    #
    # The current implementation below is a rough draft.
    # However, the equality shall still be use for testing.

    def as_set_of_faces(self):
        return set(tuple(tuple(vertex) for vertex in face) for face in self.vertices[self.faces])

    @staticmethod
    def from_set_of_faces(set_of_faces):
        faces = []
        vertices = []
        for face in set_of_faces:
            face_ids = []
            for vertex in face:
                if vertex in vertices:
                    i = vertices.index(vertex)
                else:
                    i = len(vertices)
                    vertices.append(vertex)
                face_ids.append(i)
            faces.append(face_ids)
        return Mesh(vertices=vertices, faces=faces)

    def __eq__(self, other):
        if not isinstance(other, Mesh):
            return NotImplemented
        else:
            return self.as_set_of_faces() == other.as_set_of_faces()

    def __hash__(self):
        # Really not optimal...
        return hash(frozenset(self.as_set_of_faces()))

    ##################
    #  Mesh quality  #
    ##################

    def merge_duplicates(self, **kwargs):
        return merge_duplicates(self, **kwargs)

    def heal_normals(self, **kwargs):
        return heal_normals(self, **kwargs)

    def remove_unused_vertices(self, **kwargs):
        return remove_unused_vertices(self, **kwargs)

    def heal_triangles(self, **kwargs):
        return heal_triangles(self, **kwargs)

    def remove_degenerated_faces(self, **kwargs):
        return remove_degenerated_faces(self, **kwargs)

    def heal_mesh(self):
        """Heals the mesh for different tests available.

        It applies:

        * Unused vertices removal
        * Degenerate faces removal
        * Duplicate vertices merging
        * Triangles healing
        * Normal healing
        """
        if self._has_faces_properties():
            self._remove_faces_properties()
        self.remove_unused_vertices()
        self.remove_degenerated_faces()
        self.merge_duplicates()
        self.heal_triangles()
        self.heal_normals()
        return

    #################
    #  Edges stats  #
    #################

    def _edges_stats(self):
        """Computes the min, max, and mean of the mesh's edge length"""
        vertices = self.vertices[self.faces]
        edge_length = np.zeros((self.nb_faces, 4), dtype=np.float)
        for i in range(4):
            edge = vertices[:, i, :] - vertices[:, i-1, :]
            edge_length[:, i] = np.sqrt(np.einsum('ij, ij -> i', edge, edge))

        return edge_length.min(), edge_length.max(), edge_length.mean()

    @property
    def min_edge_length(self):
        """The mesh's minimum edge length"""
        return self._edges_stats()[0]

    @property
    def max_edge_length(self):
        """The mesh's maximum edge length"""
        return self._edges_stats()[1]

    @property
    def mean_edge_length(self):
        """The mesh's mean edge length"""
        return self._edges_stats()[2]

    #######################
    #  Surface integrals  #
    #######################

    def has_surface_integrals(self):
        return 'surface_integrals' in self.__internals__

    def get_surface_integrals(self):
        """Get the mesh surface integrals

        Returns
        -------
        ndarray
            The mesh surface inegrals array
        """
        if not self.has_surface_integrals():
            from capytaine.mesh.surface_integrals import compute_faces_integrals
            self.__internals__['surface_integrals'] = compute_faces_integrals(self)
        return self.__internals__['surface_integrals']

    def _remove_surface_integrals(self):
        if 'surface_integrals' in self.__internals__:
            del self.__internals__['surface_integrals']
        return

    @property
    def volume(self):
        """Get the mesh enclosed volume

        Returns
        -------
        float
            The mesh volume
        """
        normals = self.faces_normals
        sigma_0_2 = self.get_surface_integrals()[:3]

        return (normals.T * sigma_0_2).sum() / 3.

    ####################
    #  Connectivities  #
    ####################

    def _has_connectivity(self):
        return 'v_v' in self.__internals__

    def _remove_connectivity(self):
        if 'v_v' in self.__internals__:
            del self.__internals__['v_v']
            del self.__internals__['v_f']
            del self.__internals__['f_f']
            del self.__internals__['boundaries']
        return

    @property
    def vv(self):
        """Get the vertex / vertex connectivity dictionary.

        Returns
        -------
        dict
        """
        if 'v_v' not in self.__internals__:
            self.__internals__.update(connectivity(self))
        return self.__internals__['v_v']

    @property
    def vf(self):
        """Get the vertex / faces connectivity dictionary.

        Returns
        -------
        dict
        """
        if 'v_f' not in self.__internals__:
            self.__internals__.update(connectivity(self))
        return self.__internals__['v_f']

    @property
    def ff(self):
        """Get the face / faces connectivity dictionary

        Returns
        -------
        dict
        """
        if 'f_f' not in self.__internals__:
            self.__internals__.update(connectivity(self))
        return self.__internals__['f_f']

    @property
    def boundaries(self):
        """Get the list of boundaries of the mesh.

        Returns
        -------
        list
            list that stores lists of boundary connected vertices


        Note
        ----
        The computation of boundaries should be in the future computed with help of VTK
        """
        if 'boundaries' not in self.__internals__:
            self.__internals__.update(connectivity(self))
        return self.__internals__['boundaries']

    @property
    def nb_boundaries(self):
        """Get the number of boundaries in the mesh

        Returns
        -------
        list
            Number of boundaries
        """
        if 'boundaries' not in self.__internals__:
            self.__internals__.update(connectivity(self))
        return len(self.__internals__['boundaries'])
