# Character inputs and Omni prompts

Use the existing brand project and selected Characters across scenes. Do not
create a new project or duplicate Character for each clip or retry.

## Images and saved info

For a two-image identity setup, use a single close-up showing the face and upper
body in the portrait slot, and a single full-body image showing proportions and
clothing/accessories in the full-body slot. Keep identity, age, markings and
lighting consistent across the pair. A tall image is not necessarily a useful
portrait. Avoid extra subjects, text and conflicting scenery. This is a practical
setup, not a documented requirement for a particular aspect ratio or a guarantee
that two images always outperform one. Respect an owner's approved imagery.

Flow supports one or two Character images. Its public documentation does not
specify image weights or a precedence rule between images and Character info.
Save stable identity/personality in Character info; put the scene's important
acting and appearance requirements in the video prompt as well. Do not treat
Personality as a proven direct-generation control or as a way to repair a wrong
image attachment.

Use `gflow_character_show(project, entity_id=...)` to inspect the saved reference
workflow/media IDs, and preview the actual images through an available viewer
when checking identity. The name and ID alone do not prove the right images were
saved. If previewing is unavailable, report that evidence gap.

`gflow_character_update_images` replaces only supplied slots and preserves
metadata/omitted slots. It does not update Personality. Use a canonical UUID
`operation_id`; replay the same operation only with identical inputs. A partial
update can persist if an upload fails: inspect the result and fresh Character
before a new operation, rather than blindly uploading again.

For a new Character, `gflow_character_import` accepts one source image through
the compatibility parameter `sheet_path`, plus `project`, `name`, `operation_id`
and optional `personality`. The parameter name does not require a collage. If
using separate portrait/body inputs, inspect the import result and then set the
two slots explicitly with `gflow_character_update_images`. Do not silently pick
an existing same-name Character or generate replacement images.

The legacy CLI Character body-generation path constructs a three-angle triptych.
When the user wants a single full-body reference, import/update their supplied
file instead of invoking that image-generation path.

## Three authoring forms

1. Native `@Character` beside its role/action is easy to read and matches Google's
   examples. Select the real Character, not plain text with an `@` prefix.
2. Attach Characters first, then identify each by name in the scene text. Do not
   call a Character "image 1": a Character may contain two images.
3. Attach raw images without Characters and map every image to its role. A pair
   of portrait/body images depicts one identity, not two actors. Check actual
   attachment order before using ordinal labels; these labels are prose, not a
   documented special syntax. Use actual asset tags where the interface supports them.

AutoFlow's current mention resolver extracts IDs and retains display names in
text; its migrated composer attaches images, then Character chips, then appends
the prompt. It does not preserve the original inline chip position. Therefore
moving `@Name` around in an AutoFlow prompt is not by itself a test of native
inline placement versus prefixed chips. Do not claim either form improves likeness
without comparing the submitted inputs and resulting media.

## Compact prompt pattern

```text
@A is the saved puppy in the teal harness. @B is the saved calico kitten.
Keep B's orange forehead and flank patches as shown in B's Character images.
They are a playful couple on their sofa. The goal is an affectionate exchange.
A asks in Thai: "วันนี้อยากกินขนมอะไรครับ?"
B replies knowingly: "เลือกให้หน่อย แต่ขออร่อยนะ!"
Photorealistic, natural light, both faces readable, brisk natural conversation.
```

`A` and `B` are placeholders for real project Characters. This is an original
example, not a measured best prompt. For product scenes, identify the product and
environment references separately and include only verified product information.
Let the model fill ordinary staging details; specify timing/continuity only where
it changes the intended story.

After a mismatch, first inspect the saved slots and actual attachment. If those
are correct, change one hypothesis at a time (for example one marking reminder),
keeping the other inputs stable. Compare output to the reference and record
what changed. A single successful sample is not proof of all-case consistency.
Use the user's QC interval; do not turn one project's sampling choice into a
universal requirement or change references to match a drifted output.

## Official sources

Checked 2026-10-11; availability and model behavior may change:

- [Character creation and optional info](https://support.google.com/flow/answer/16935308?hl=en)
- [Character tags, ingredient roles and clean references](https://support.google.com/flow/answer/16353334?hl=en)
- [Omni intent, references and scene direction](https://deepmind.google/models/gemini-omni/prompt-guide/)
