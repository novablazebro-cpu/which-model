# Learning to code with this project

You are learning while we build. The order that works best for a complete beginner:

1. **Read before you write.** Open a short file such as `axiom3d/checks/blocks.py`. Code is mostly plain
   English words; try to say out loud what each line does. Ask about any line you can't read.
2. **Learn the saving system (git).** Commits, branches, push and pull requests are how all professional
   code is saved and shared. See [glossary.md](glossary.md).
3. **Python basics, through this project's files:**
   - variables
   - `if` decisions
   - lists and `for` loops
   - functions (`def`)
   - classes
   Every one of them appears in `axiom3d/model/blocks.py`.
4. **Tests.** Read `tests/test_blocks.py` next to `axiom3d/model/blocks.py`: each test is a small, exact
   statement of what the code must do.
5. **Change one small thing yourself,** run the tests (`uv run pytest -q`), and see what turns red.

New terms go into [glossary.md](glossary.md) as they come up.
