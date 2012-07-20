from dolfin import Mesh, UnitSquare, compile_subdomains
import os
import numpy as np

class SampleDomain(object):
    @classmethod
    def setupDomain(cls, name, **kwargs):
        _domains = {'lshape':cls._lshape, 'square':cls._square, 'cooks':cls._cooks}
        return _domains[name](**kwargs)
    
    @classmethod
    def _lshape(cls, **kwargs):
        lshape_xml = os.path.join(os.path.dirname(__file__), 'lshape.xml')
        mesh0 = Mesh(lshape_xml)
        maxx, minx, maxy, miny = 1, -1, 1, -1
        # setup boundary parts
        top, bottom, left, right = compile_subdomains([  'near(x[1], maxy) && on_boundary',
                                                         'near(x[1], miny) && on_boundary',
                                                         'near(x[0], minx) && on_boundary',
                                                         'near(x[0], maxx) && on_boundary'])
        top.maxy = maxy
        bottom.miny = miny
        left.minx = minx
        right.maxx = maxx
        return mesh0, {'top':top, 'bottom':bottom, 'left':left, 'right':right}

    @classmethod
    def _square(cls, **kwargs):
        N = kwargs['initial_mesh_N']
        mesh0 = UnitSquare(N, N)
        maxx, minx, maxy, miny = 1, 0, 1, 0
        # setup boundary parts
        top, bottom, left, right = compile_subdomains([  'near(x[1], maxy) && on_boundary',
                                                         'near(x[1], miny) && on_boundary',
                                                         'near(x[0], minx) && on_boundary',
                                                         'near(x[0], maxx) && on_boundary'])
        top.maxy = maxy
        bottom.miny = miny
        left.minx = minx
        right.maxx = maxx
        return mesh0, {'top':top, 'bottom':bottom, 'left':left, 'right':right}

    @classmethod
    def _cooks(cls, **kwargs):
        mesh = UnitSquare(10, 5)
        def cooks_domain(x, y):
            return [48 * x, 44 * (x + y) - 18 * x * y]
        mesh.coordinates()[:] = np.array(cooks_domain(mesh.coordinates()[:, 0], mesh.coordinates()[:, 1])).transpose()
    #    plot(mesh, interactive=True, axes=True) 
        maxx, minx, maxy, miny = 48, 0, 60, 0
        # setup boundary parts
        llc, lrc, tlc, trc = compile_subdomains(['near(x[0], minx) && near(x[1], miny)',
                                                         'near(x[0], maxx) && near(x[1], miny)',
                                                         'near(x[0], minx) && near(x[1], maxy)',
                                                         'near(x[0], maxx) && near(x[1], maxy)'])    
        top, bottom, left, right = compile_subdomains([  'x[0] > minx && x[0] < maxx && x[1] >= 44. && on_boundary',
                                                         'x[0] > minx && x[0] < maxx && x[1] <= 44. && on_boundary',
                                                         'near(x[0], minx) && on_boundary',
                                                         'near(x[0], maxx) && on_boundary'])    
        # the corners
        llc.minx = minx
        llc.miny = miny
        lrc.maxx = maxx
        lrc.miny = miny
        tlc.minx = minx
        tlc.maxy = maxy
        trc.maxx = maxx
        trc.maxy = maxy
        # the edges
        top.minx = minx
        top.maxx = maxx
        bottom.minx = minx
        bottom.maxx = maxx
        left.minx = minx
        right.maxx = maxx
        return mesh, {'top':top, 'bottom':bottom, 'left':left, 'right':right, 'llc':llc, 'lrc':lrc, 'tlc':tlc, 'trc':trc}
