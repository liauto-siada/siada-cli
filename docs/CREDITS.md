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
- **Attribution**: Copyright (c) 2025 OpenHands contributors (as stated in the upstream [LICENSE](https://github.com/All-Hands-AI/OpenHands/blob/main/LICENSE)).
- **Contribution & Modifications**: Quoted the code from its file editing tool and modified its parameters to adapt to the openai-agent-sdk.

### [Codex](https://github.com/openai/codex)
- **License**: Apache 2.0
- **Contribution & Modifications**: Referenced its skills module implementation and adapted it to our own skills system, including the field limits, prompt wording, and the skills list rendering budget and degradation design.
- **Attribution (from the Codex NOTICE file)**: OpenAI Codex, Copyright 2025 OpenAI.
- **GPT-5 personality guidance**: adapted `codex-rs/core/templates/personalities/gpt-5.2-codex_pragmatic.md` and `gpt-5.2-codex_friendly.md` at commit `2dbcab90e24bbe3c710ad41ffab7bb372256827b`, changing the identity and tool guidance for Siada. The Apache-2.0 license and Codex attribution above apply.
- **GPT-6 templates**: the packaged GPT-6 templates (`siada/agent_hub/coder/prompt/models/gpt6/templates/`) are modified versions of Codex's `model_messages.instructions_template` entries in `codex-rs/models-manager/models.json` (source commit `2fdf047c9631c9ed01a31b62efb7891718a931a8`, 2026-10-08; models catalog commit `d63a9b8344cfe58bc78bbe319b560378fc8756ef`, 2026-10-06). They stay under the Apache 2.0 license and the attribution above; the individual modifications are listed in that directory's `README.md`.

### [ZCode](https://github.com/zai-org/ZCode)
- **License**: Apache 2.0 ([LICENSE](https://github.com/zai-org/ZCode/blob/main/LICENSE); the repository states that its first-party code is Apache-2.0 in [NOTICE.md](https://github.com/zai-org/ZCode/blob/main/NOTICE.md), section "第三方许可与版权声明").
- **Attribution**: Copyright 2026 Z.AI Co., Ltd, as stated in the LICENSE at commit `29628c9acdb81b703bbd4080c207a0e7ce5e276e`; the Apache-2.0 license text below applies.
- **Contribution & Modifications**: adapted the identity/harness and communication structure of the public ZCode CLI at commit 29628c9 (`apps/zcode-cli/packages/core/src/context/sections/cli-prefix.ts`, `.../sections/identity.ts` and `.../context/dynamic-sections.ts`) for the GLM-5.2-and-later prompt profile. All wording was rewritten for Siada's tools, permission model and safety rules, and ZCode product identifiers were removed.
- **Todo reminder**: adapted `apps/zcode-cli/packages/core/src/runtime/helpers/runtime-reminders.ts` at the same commit, changing tool names and the reminder's presentation for Siada.

### [Kimi Code](https://github.com/MoonshotAI/kimi-code)
- **License**: MIT ([LICENSE](https://github.com/MoonshotAI/kimi-code/blob/main/LICENSE)).
- **Attribution**: Copyright (c) 2026 Moonshot AI. The MIT permission notice is reproduced below and applies to the adapted template.
- **Contribution & Modifications**: adapted the system-prompt template structure for the Kimi K3-and-later prompt (`siada/agent_hub/coder/prompt/models/kimi_k3/templates/system.md`); runtime facts and the available tools are adapted to Siada.

### [chrome-acp](https://github.com/Areo-Joe/chrome-acp)
- **License**: MIT
- **Attribution**: Copyright (c) 2025 Areo-Joe.
- **Contribution & Modifications**: Adapted the browser extension and proxy for Siada, including browser tools, recording, remote access, and the activity trace. Its original [license](../chrome-acp/LICENSE) is retained.
- **Third-party components**: the extension, proxy and PWA bundles ship their own notices and license texts, see [chrome-acp/THIRD_PARTY_NOTICES.md](../chrome-acp/THIRD_PARTY_NOTICES.md).

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
