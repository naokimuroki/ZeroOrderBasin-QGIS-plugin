def classFactory(iface):
    from .plugin import ZeroOrderBasin
    return ZeroOrderBasin(iface)