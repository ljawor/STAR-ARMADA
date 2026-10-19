# Publication autocrlf closure

A real network clone at initial S08 head `e82345f64eadbbe5366e6dfc82ecdb3a85212ac7`, checked out with `git -c core.autocrlf=true clone`, passed all 35 focused headless tests and model validation but metadata reproduction failed on the pre-existing raw renderer pin. The original attributes omitted `render/renderer.py`; CRLF conversion changed only checkout bytes, not its committed source. `metadata-red.txt` is the actual failed output.

The follow-up adds only a scoped `render/renderer.py -text` attribute and this evidence/receipt update. It does not normalize, edit, rebuild or reapprove the renderer or any asset. This is a pure checkout configuration fix; all 1,225 final integrated source inputs remain identical to the tested bytes. The exact follow-up head and fresh autocrlf clone GREEN reproduction are published in the PR comment, avoiding a self-referential commit receipt. No native Windows graphics/pipeline or frozen package acceptance is inferred.
