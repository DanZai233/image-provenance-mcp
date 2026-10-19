# fixtures

Empty by design. Every test builds its fixtures at runtime in a temporary
directory — see `tests/fixture_builders.py`.

Nothing here is a real photograph and nothing here belongs to a person: the
signed fixture is assembled byte by byte by the test suite, carries no
certificate chain, and exists to prove the parser reads a manifest, not to prove
anything about the world. Keeping binaries out of the repository means no
image of an ID card, a seal, or a location watermark can ever be committed by
accident.

If you want to check the reader against a real Content Credential, point the CLI
at a file you own:

```bash
image-provenance /path/to/your/signed-image.jpg
```
