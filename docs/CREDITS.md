# Credits

## Open Source Projects

Siada CLI incorporates and adapts from the following open source projects. We are deeply grateful for their contributions to the open source community:

### [Cline](https://github.com/cline/cline)
- **License**: Apache 2.0
- **Contribution & Modifications**: Referenced its prompt design and made changes to tool usage and rules.

### [Aider](https://github.com/paul-gauthier/aider)
- **License**: Apache 2.0
- **Contribution & Modifications**: Referenced its interaction approach and made modifications including @command handling, streaming output, and other changes. Also drew inspiration from its excellent repo map design concept.

### [OpenHands](https://github.com/All-Hands-AI/OpenHands)
- **License**: MIT
- **Contribution & Modifications**: Quoted the code from its file editing tool and modified its parameters to adapt to the openai-agent-sdk.

### [Codex](https://github.com/openai/codex)
- **License**: Apache 2.0
- **Contribution & Modifications**: Referenced its skills module implementation and adapted it to our own skills system, including the field limits, prompt wording, and the skills list rendering budget and degradation design.
- **GPT-6 templates**: Adapted the corresponding GPT-6 Astra, GPT-6.1 Sol, GPT-6 Sol, and GPT-6 Luna prompt sections from commit `2fdf047c9631c9ed01a31b62efb7891718a931a8`. Identity, tool names, message channels, skill providers, and unavailable question/connector/plugin/approval-review mechanisms are adapted to Siada. See `siada/agent_hub/coder/prompt/models/gpt6/templates/README.md` for source paths and modifications.
- **GPT-6.1 Terra**: Reuses its Astra-equivalent main template and adapts the additional execution preference from `model_messages.collaboration_modes.default` in models catalog commit `126a0ee92ed2c5e73cd8a8f7e37563e8527552d7`. The Codex-only Default-mode qualifier is omitted for Siada's coding prompt.
- **GPT-6 and later delegation policy**: Adapted the V2 explicit-request delegation rule from commit `83086188ae0614bd882818ff1aa23f3194962012` (`codex-rs/prompts/src/model_messages/multi_agent.rs`) and the neutral tool introduction from `codex-rs/core/src/tools/handlers/multi_agents_spec.rs` to Siada's `run_subtask` tool.
- **Attribution (from the Codex NOTICE file)**: OpenAI Codex, Copyright 2025 OpenAI.

### [@napi-rs/clipboard](https://github.com/Brooooooklyn/Clipboard)

- **License**: MIT.
- **Usage**: Unchanged native clipboard bindings, based on
  [arboard](https://github.com/1Password/arboard) (MIT OR Apache-2.0), provide
  desktop text clipboard reads and writes. The packaged helper includes the
  original package metadata and a license notice.

### [@mariozechner/clipboard](https://github.com/badlogic/clipboard)

- **License**: MIT.
- **Usage**: Native desktop image clipboard reads and PNG encoding. Version
  0.3.6 supplies the prebuilt modules used by the image helper. It is based on
  [CrossCopy/clipboard](https://github.com/CrossCopy/clipboard) and
  [clipboard-rs](https://github.com/ChurchTao/clipboard-rs).

### [ZCode](https://github.com/zai-org/ZCode)
- **License**: Apache 2.0
- **Contribution & Modifications**: The GLM-5.2-and-later system prompt copies its CLI system prompt (commit 29628c9: `apps/zcode-cli/packages/core/src/context/sections/identity.ts`, `dynamic-sections.ts`, and the `env-info.ts` layout) with the product identity renamed to Siada and runtime facts (working directory, platform, home directory, username) substituted by Siada. Its one-line CLI prefix message, git-status snapshot, persistent-memory, and tool-specific sections are not copied; Siada's own capabilities, safety rules, and catalogs apply. Also referenced its runtime todo reminder behavior for empty todo lists.

### [Kimi Code](https://github.com/MoonshotAI/kimi-code)

- **License**: MIT
- **Contribution & Modifications**: Adapted `packages/agent-core-v2/src/app/agentProfileCatalog/system.md` and its terminal reply style from commit `72fc1d0a3` for the Kimi K3 prompt. Identity, tools, environment, compaction behavior, skills, and memory injection are adapted to Siada.
- **Copyright**: Copyright (c) 2026 Moonshot AI. The MIT permission notice is reproduced below and applies to the adapted template.

### [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)

- **License**: MIT
- **Contribution & Modifications**: Adapted the `dsh@0.2.1-rc.2` system-prompt identity, coding persona, file/search/command guidance, skill-loading instructions, delegation guidance, and web-content trust instructions from commit `687f282e8625c6b8d11ff58211a90524be2e4317`. Identity and tool contracts are adapted to Siada; unsupported Harness tools and Web-only context are omitted. Source paths and modifications are listed in `siada/agent_hub/coder/prompt/models/deepseek/templates/README.md`.
- **Copyright**: Copyright (c) 2026 DeepSeek. The MIT permission notice reproduced below applies to the adapted templates.


## Open Source licenses

### MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

### Apache License 2.0


                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]
