# Meshvenn Humanoid Quality

Install the independent ZIP through Blender 5.2's **Preferences → Get Extensions → Install from Disk**, after enabling Meshvenn. Enable **Meshvenn Humanoid Quality**. Its Meshvenn sidebar panel controls automatic checks, the report folder and the time budget. If the engine was enabled later, press **Connect humanoid quality loop**.

Every new Canonical Biped V2 rig then runs through an isolated quality worker before the pipeline continues. The worker poses both shoulders and elbows, exports/reimports candidates and regenerates local arm weights when needed. It rejects collapsed or inverted elbow surfaces, unexpected link motion and transport changes. A passing candidate transfers its weights to the same scene objects. An unresolved humanoid stops the pipeline and retains its report. A non-native/non-humanoid source is skipped with an explicit reason. Animation migration and Stytch consumer acceptance are outside this profile.

The extension bundles `meshvenn-humanoid`; it does not bundle or modify the engine. Disable automatic checks in its panel to bypass supervision. Unregistering it restores the original rig implementation. Input snapshots and reports remain in the chosen report folder.

Build the wheel with `python -m pip wheel --no-deps --no-build-isolation packages/meshvenn_humanoid --wheel-dir dist/humanoid`, then run `python scripts/build_humanoid_extension.py --wheel dist/humanoid/meshvenn_humanoid-0.1.0-py3-none-any.whl`. Validate the resulting ZIP with `blender --command extension validate dist/meshvenn_humanoid_auto-0.1.0.zip`.
