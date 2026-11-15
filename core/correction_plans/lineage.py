"""Accepted design ancestry is allowed; target-derived truth is not."""


def accepted_references(view_set,target=None):
    canonical=view_set.canonical_reference
    if canonical is None or not canonical.validated or canonical.validation_evidence is None:
        return ()
    graph={}
    for view in view_set.views:
        for content in (view.image,view.mask):
            if content:
                graph.setdefault(content.sha256,set()).update(view.derived_from)
    target_hashes={c.sha256 for c in (target.image,target.mask) if c} if target else set()
    def valid(reference):
        active,done=set(),set()
        def visit(value):
            if value in active or value in target_hashes:
                return False
            if value in done:
                return True
            active.add(value)
            if any(not visit(p) for p in graph.get(value,())):
                return False
            active.remove(value)
            done.add(value)
            return True
        return all(visit(parent) for parent in reference.derived_from)
    return tuple(v for v in view_set.views if v.view_id in canonical.view_ids and v.role=="reference" and v.image
                 and v.camera.verified and v.camera.verification_evidence and v.camera.projection=="orthographic"
                 and v!=target and valid(v))
