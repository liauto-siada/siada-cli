/**
 * Plugin Manager Component
 * TUI for discovering, installing, and managing skills/plugins
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { PickerHeader, PickerFooter, PickerRow, PickerScrollHint, calculatePickerVisibleCount } from '../Picker/Picker.js';
import { colors } from '../../utils/colors.js';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';

// ─── Types ─────────────────────────────────────────────────────────────────

export interface SkillInfo {
  name: string;
  description: string;
  scope: 'user' | 'repo' | 'system';
  path: string;
  isMcp?: boolean;
  plugin_name?: string | null;
}

export interface MCPServerInfo {
  name: string;
  command: string;
  args: string[];
  url: string;
}

export interface MarketplaceInfo {
  name: string;
  repo: string;
  available: number;
  installed: number;
  updatedAt?: string;
}

export interface PluginError {
  path: string;
  message: string;
  scope: string;
}

export interface DiscoverSkill {
  name: string;
  description: string;
  marketplace: string;
  marketplaceName: string;
  installed: boolean;
  installs?: string;
}

export interface PluginManagerData {
  installed: SkillInfo[];
  marketplaces: MarketplaceInfo[];
  errors: PluginError[];
  discover: DiscoverSkill[];
  disabledSkills?: string[];
  mcp_servers?: MCPServerInfo[];
}

export interface InstallProgress {
  skillName: string;
  phase: string;
  percent: number;
}

export interface PluginManagerProps {
  data: PluginManagerData;
  installProgress?: InstallProgress | null;
  onAction: (message: string) => void;
  onExit: () => void;
}

// ─── Constants ─────────────────────────────────────────────────────────────

const TABS = ['Discover', 'Installed', 'Marketplaces'] as const;
type TabName = typeof TABS[number];

// ─── Component ─────────────────────────────────────────────────────────────

export const PluginManager: React.FC<PluginManagerProps> = ({ data, installProgress, onAction, onExit }) => {
  const uiLanguage = useUiLanguage();
  const { rows } = useTerminalSize();
  // Include each item's description and group header in the visible-row budget.
  const MAX_VISIBLE = calculatePickerVisibleCount(rows, { summary: true, rowHeight: 3, extraRows: 2 });

  const [activeTab, setActiveTab] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);

  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  const [isAddingMarketplace, setIsAddingMarketplace] = useState(false);
  const [addInput, setAddInput] = useState('');

  const [localInstalled, setLocalInstalled] = useState<Set<string>>(() => {
    const names = new Set(data.installed.map(s => s.name));
    // Also seed with marketplace plugin names that are already installed
    // (plugin name != skill name, e.g. "hookify" vs "Writing Hookify Rules")
    for (const skill of data.discover) {
      if (skill.installed) names.add(skill.name);
    }
    return names;
  });
  const [localDisabled, setLocalDisabled] = useState<Set<string>>(
    () => new Set(data.disabledSkills ?? [])
  );
  const [localRemovedSkills, setLocalRemovedSkills] = useState<Set<string>>(new Set());
  const [localRemovedMps, setLocalRemovedMps] = useState<Set<string>>(new Set());
  const [localExtraMarketplaces, setLocalExtraMarketplaces] = useState<MarketplaceInfo[]>([]);
  // Fallback status message shown before first progress notification arrives
  const [pendingMsg, setPendingMsg] = useState<string>('');
  useEffect(() => {
    if (!pendingMsg) return;
    const t = setTimeout(() => setPendingMsg(''), 90_000);
    return () => clearTimeout(t);
  }, [pendingMsg]);
  // Clear pendingMsg as soon as real progress (or completion) arrives
  useEffect(() => {
    setPendingMsg('');
  }, [installProgress]);
  // Clear pendingMsg when backend refreshes the data (signals action completed)
  useEffect(() => {
    setPendingMsg('');
  }, [data]);

  // Sync localInstalled when data refreshes (e.g. after install/remove)
  useEffect(() => {
    setLocalInstalled(prev => {
      const names = new Set(data.installed.map((s: SkillInfo) => s.name));
      for (const skill of data.discover) {
        if (skill.installed) names.add(skill.name);
      }
      // Preserve any optimistic adds that aren't yet reflected in data
      for (const name of prev) {
        names.add(name);
      }
      return names;
    });
  }, [data]);

  // ─── Derived ─────────────────────────────────────────────────────────────

  const discoverSkills = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return data.discover.filter(
      s => !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
    );
  }, [data.discover, searchQuery]);

  // Flat list of selectable items for navigation (no headers)
  type InstalledSkillEntry = SkillInfo & { isMcp: boolean };

  const installedSkills = useMemo((): InstalledSkillEntry[] => {
    const skills = data.installed
      .filter(s => !localRemovedSkills.has(s.name))
      .map(s => ({ ...s, isMcp: false as const }));
    const mcps = (data.mcp_servers || []).map(m => ({
      name: m.name,
      description: m.url ? `HTTP: ${m.url}` : `stdio: ${m.command}${m.args.length ? ' ' + m.args.join(' ') : ''}`,
      scope: 'system' as const,
      path: m.url || m.command,
      isMcp: true as const,
      plugin_name: null,
    }));
    return [...skills, ...mcps];
  }, [data.installed, data.mcp_servers, localRemovedSkills, uiLanguage]);

  // Grouped structure for rendering: section headers + selectable items
  // Each entry is either a header (no selectIdx) or a skill with its navigation index
  type SectionHeader = { kind: 'header'; label: string };
  type SectionSkill = { kind: 'skill'; skill: InstalledSkillEntry; selectIdx: number };
  type SectionEntry = SectionHeader | SectionSkill;

  const installedSections = useMemo((): SectionEntry[] => {
    const skills = data.installed
      .filter(s => !localRemovedSkills.has(s.name))
      .map(s => ({ ...s, isMcp: false as const }));
    const mcps = (data.mcp_servers || []).map(m => ({
      name: m.name,
      description: m.url ? `HTTP: ${m.url}` : `stdio: ${m.command}${m.args.length ? ' ' + m.args.join(' ') : ''}`,
      scope: 'system' as const,
      path: m.url || m.command,
      isMcp: true as const,
      plugin_name: null,
    }));

    const entries: SectionEntry[] = [];
    let selectIdx = 0;

    // Group plugin skills by plugin_name
    const pluginMap = new Map<string, InstalledSkillEntry[]>();
    const standaloneSkills: InstalledSkillEntry[] = [];
    for (const s of skills) {
      if (s.plugin_name) {
        const existing = pluginMap.get(s.plugin_name) ?? [];
        existing.push(s);
        pluginMap.set(s.plugin_name, existing);
      } else {
        standaloneSkills.push(s);
      }
    }

    if (pluginMap.size > 0) {
      entries.push({ kind: 'header', label: t(`插件（${pluginMap.size}）`, `Plugins (${pluginMap.size})`) });
      for (const [pname, pskills] of pluginMap) {
        entries.push({ kind: 'header', label: `  \u25b8 ${pname}` });
        for (const s of pskills) {
          entries.push({ kind: 'skill', skill: s, selectIdx: selectIdx++ });
        }
      }
    }

    if (standaloneSkills.length > 0) {
      entries.push({ kind: 'header', label: t(`技能（${standaloneSkills.length}）`, `Skills (${standaloneSkills.length})`) });
      for (const s of standaloneSkills) {
        entries.push({ kind: 'skill', skill: s, selectIdx: selectIdx++ });
      }
    }

    if (mcps.length > 0) {
      entries.push({ kind: 'header', label: t(`MCP 服务（${mcps.length}）`, `MCP Servers (${mcps.length})`) });
      for (const m of mcps) {
        entries.push({ kind: 'skill', skill: m, selectIdx: selectIdx++ });
      }
    }

    return entries;
  }, [data.installed, data.mcp_servers, localRemovedSkills, uiLanguage]);

  const visibleMarketplaces = useMemo(
    () =>
      [...data.marketplaces, ...localExtraMarketplaces].filter(
        m => !localRemovedMps.has(m.name)
      ),
    [data.marketplaces, localExtraMarketplaces, localRemovedMps]
  );

  const getItemCount = useCallback(
    (tabIdx: number): number => {
      switch (tabIdx) {
        case 0:
          return discoverSkills.length;
        case 1:
          return installedSkills.length;
        case 2:
          return visibleMarketplaces.length + 1;
        default:
          return 0;
      }
    },
    [discoverSkills.length, installedSkills.length, visibleMarketplaces.length]
  );

  const switchTab = useCallback((delta: number) => {
    setActiveTab(t => {
      const next = (t + delta + TABS.length) % TABS.length;
      setActiveIndex(0);
      return next;
    });
  }, []);

  const moveSelection = useCallback(
    (delta: number) => {
      setActiveIndex(i => {
        const count = getItemCount(activeTab);
        if (count === 0) return 0;
        const next = i + delta;
        return next < 0 ? 0 : next >= count ? count - 1 : next;
      });
    },
    [activeTab, getItemCount]
  );

  // ─── Keyboard ────────────────────────────────────────────────────────────

  useKeypress(key => {
    // Add-marketplace text input mode
    if (isAddingMarketplace) {
      if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
        setIsAddingMarketplace(false);
        setAddInput('');
      } else if (key.name === 'return') {
        const repo = addInput.trim();
        if (repo) {
          const namePart = repo.split('/').pop() ?? repo;
          onAction(`/plugin marketplace add ${repo}`);
          setLocalExtraMarketplaces(ms => [
            ...ms,
            { name: namePart, repo, available: 0, installed: 0 },
          ]);
        }
        setIsAddingMarketplace(false);
        setAddInput('');
      } else if (key.name === 'backspace' || key.name === 'delete') {
        setAddInput(s => s.slice(0, -1));
      } else if (key.insertable && !key.ctrl && !key.cmd) {
        setAddInput(s => s + key.sequence);
      }
      return;
    }

    // Search mode
    if (isSearching) {
      if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
        setIsSearching(false);
        setSearchQuery('');
        setActiveIndex(0);
      } else if (key.name === 'return') {
        setIsSearching(false);
      } else if (key.name === 'backspace' || key.name === 'delete') {
        setSearchQuery(s => s.slice(0, -1));
      } else if (key.insertable && !key.ctrl && !key.cmd) {
        setSearchQuery(s => s + key.sequence);
        setActiveIndex(0);
      }
      return;
    }

    // Tab navigation
    if (key.name === 'tab') {
      switchTab(key.shift ? -1 : 1);
      return;
    }
    if (key.name === 'right') {
      switchTab(1);
      return;
    }
    if (key.name === 'left') {
      switchTab(-1);
      return;
    }
    if (key.name === 'escape' || (key.ctrl && key.name === 'c')) {
      onExit();
      return;
    }

    // List navigation
    if (key.name === 'up' || key.sequence === 'k') {
      moveSelection(-1);
      return;
    }
    if (key.name === 'down' || key.sequence === 'j') {
      moveSelection(1);
      return;
    }
    if (key.name === 'pageup') {
      moveSelection(-MAX_VISIBLE);
      return;
    }
    if (key.name === 'pagedown') {
      moveSelection(MAX_VISIBLE);
      return;
    }

    // Tab-specific actions
    const tabName: TabName = TABS[activeTab];

    if (tabName === 'Discover') {
      if (key.sequence === '/') {
        setIsSearching(true);
        setActiveIndex(0);
        return;
      }
      const skill = discoverSkills[activeIndex];
      if (!skill) return;
      if (key.sequence === ' ' || key.name === 'return') {
        const isInstalled = localInstalled.has(skill.name);
        if (isInstalled) {
          setLocalInstalled(s => {
            const ns = new Set(s);
            ns.delete(skill.name);
            return ns;
          });
          setLocalRemovedSkills(s => new Set([...s, skill.name]));
          setPendingMsg(t(`正在卸载“${skill.name}”…`, `Removing '${skill.name}'...`));
          onAction(`/plugin remove ${skill.name}`);
        } else {
          setLocalInstalled(s => new Set([...s, skill.name]));
          setPendingMsg(t('等待开始下载…', 'Waiting for clone to start...'));
          onAction(`/plugin install ${skill.name} @${skill.marketplaceName}`);
        }
      }
    } else if (tabName === 'Installed') {
      const skill = installedSkills[activeIndex];
      if (!skill) return;
      if (skill.isMcp) return; // MCP servers cannot be disabled/removed from TUI
      if (key.sequence === 'd' || key.sequence === 'D') {
        if (localDisabled.has(skill.name)) {
          setLocalDisabled(s => {
            const ns = new Set(s);
            ns.delete(skill.name);
            return ns;
          });
          onAction(`/plugin enable ${skill.name}`);
        } else {
          setLocalDisabled(s => new Set([...s, skill.name]));
          onAction(`/plugin disable ${skill.name}`);
        }
      } else if (key.sequence === 'r' || key.sequence === 'R') {
        setLocalRemovedSkills(s => new Set([...s, skill.name]));
        setLocalInstalled(s => {
          const ns = new Set(s);
          ns.delete(skill.name);
          return ns;
        });
        onAction(`/plugin remove ${skill.name}`);
      }
    } else if (tabName === 'Marketplaces') {
      if (activeIndex === 0 && key.name === 'return') {
        setIsAddingMarketplace(true);
        setAddInput('');
      } else if (activeIndex > 0) {
        const mp = visibleMarketplaces[activeIndex - 1];
        if (!mp) return;
        if (key.sequence === 'r' || key.sequence === 'R') {
          setLocalRemovedMps(s => new Set([...s, mp.name]));
          onAction(`/plugin marketplace remove ${mp.name}`);
        } else if (key.sequence === 'u' || key.sequence === 'U') {
          setPendingMsg(t(`正在从“${mp.name}”获取技能…`, `Fetching skills from '${mp.name}'...`));
          onAction(`/plugin marketplace update ${mp.name}`);
        }
      }
    }
  });

  // ─── Render helpers ───────────────────────────────────────────────────────

  const renderTabBar = () => (
    <Box flexDirection="column">
      <PickerHeader title={t('插件', 'Plugins')} />
      <Box flexDirection="row">
        {TABS.map((tab, i) => (
          <Text
            key={tab}
            color={activeTab === i ? undefined : colors.content.secondary}
            bold={activeTab === i}
            wrap="truncate-end"
          >
            {activeTab === i ? '› ' : '  '}{t({ Discover: '发现', Installed: '已安装', Marketplaces: '市场' }[tab], tab)}
            {'   '}
          </Text>
        ))}
      </Box>
    </Box>
  );

  const renderDiscoverTab = () => {
    const skills = discoverSkills;
    const startIdx = Math.max(0, activeIndex - MAX_VISIBLE + 1);
    const endIdx = Math.min(skills.length, startIdx + MAX_VISIBLE);
    const visible = skills.slice(startIdx, endIdx);

    return (
      <Box flexDirection="column">
        <Box>
          <Text color={colors.content.secondary} wrap="truncate-end">
            {t(`发现插件（${skills.length}/${data.discover.length}）`, `Discover plugins (${skills.length}/${data.discover.length})`)}
          </Text>
        </Box>

        <Box>
            <Text color={colors.content.secondary} wrap="truncate-end">
              {isSearching
                ? `\u2315 ${searchQuery}\u258b`
                : searchQuery
                ? `\u2315 ${searchQuery}`
                : t('⌕ 搜索…', '⌕ Search…')}
            </Text>
        </Box>

        {skills.length === 0 && (
          <Box>
            <Text color={colors.content.secondary} wrap="truncate-end">
              {data.marketplaces.length === 0
                ? t('尚未配置市场，请在“市场”标签中添加。', 'No marketplaces configured. Add one in the Marketplaces tab.')
                : searchQuery
                ? t('没有匹配的技能。', 'No skills match your search.')
                : t('已配置的市场中暂无可用技能。', 'No skills available from configured marketplaces.')}
            </Text>
          </Box>
        )}

        <PickerScrollHint visible={startIdx > 0} direction="up" />
        {visible.map((skill, relIdx) => {
          const absIdx = startIdx + relIdx;
          const isActive = absIdx === activeIndex;
          const isInstalled = localInstalled.has(skill.name);
          return (
            <Box key={skill.name} flexDirection="column">
              <PickerRow active={isActive} checked={isInstalled}>
                {`${skill.name} · ${skill.marketplaceName || skill.marketplace}${skill.installs ? t(` · ${skill.installs} 次安装`, ` · ${skill.installs} installs`) : ''}`}
              </PickerRow>
              <Box paddingLeft={2}>
                <Text color={colors.content.secondary} wrap="truncate-end">
                  {skill.description.length > 72
                    ? skill.description.slice(0, 69) + '...'
                    : skill.description}
                </Text>
              </Box>
            </Box>
          );
        })}

        <PickerScrollHint visible={endIdx < skills.length} direction="down" />

        {installProgress ? (() => {
          const filled = Math.round(Math.max(0, Math.min(100, installProgress.percent)) / 10);
          const bar = '█'.repeat(filled) + '░'.repeat(10 - filled);
          return (
            <Box>
              <Text color={colors.content.secondary} wrap="truncate-end">
                {`${bar} ${installProgress.percent}% ${installProgress.skillName} · ${installProgress.phase}`}
              </Text>
            </Box>
          );
        })() : pendingMsg ? (
          <Box>
            <Text color={colors.content.secondary} wrap="truncate-end">{`\u29d7 ${pendingMsg}`}</Text>
          </Box>
        ) : null}
      </Box>
    );
  };

  const renderInstalledTab = () => {
    const totalSelectable = installedSkills.length;
    const sections = installedSections;

    const windowStart = Math.max(0, activeIndex - MAX_VISIBLE + 1);
    const windowEnd = Math.min(totalSelectable, windowStart + MAX_VISIBLE);

    // Pre-compute which header indices have at least one visible skill after them
    // (until the next header), so we can hide irrelevant section headers when scrolled
    const visibleHeaders = new Set<number>();
    let currentHeaderIdx = -1;
    for (let i = 0; i < sections.length; i++) {
      const e = sections[i];
      if (e.kind === 'header') {
        currentHeaderIdx = i;
      } else if (currentHeaderIdx >= 0 && e.selectIdx >= windowStart && e.selectIdx < windowEnd) {
        visibleHeaders.add(currentHeaderIdx);
      }
    }

    return (
      <Box flexDirection="column">
        <Box>
          <Text color={colors.content.secondary} wrap="truncate-end">
            {t(`已安装（${totalSelectable}）`, `Installed (${totalSelectable})`)}
          </Text>
        </Box>

        {totalSelectable === 0 && (
          <Box>
            <Text color={colors.content.secondary} wrap="truncate-end">{t('尚未安装技能、插件或 MCP 服务。', 'No skills, plugins or MCP servers installed.')}</Text>
          </Box>
        )}

        <PickerScrollHint visible={windowStart > 0} direction="up" />

        {sections.map((entry, i) => {
          if (entry.kind === 'header') {
            if (!visibleHeaders.has(i)) return null;
            const isTopLevel = !entry.label.startsWith('  ');
            return (
              <Box key={`hdr-${i}`}>
                <Text color={colors.content.secondary} bold={isTopLevel} wrap="truncate-end">
                  {entry.label}
                </Text>
              </Box>
            );
          }
          if (entry.selectIdx < windowStart || entry.selectIdx >= windowEnd) return null;
          const { skill, selectIdx } = entry;
          const isActive = selectIdx === activeIndex;
          const isDisabled = localDisabled.has(skill.name);
          const scopeLabel = skill.isMcp
            ? '[mcp]'
            : skill.scope === 'user'
            ? t('[用户]', '[user]')
            : skill.scope === 'repo'
            ? t('[项目]', '[repo]')
            : t('[系统]', '[sys]');
          return (
            <Box key={skill.name} flexDirection="column">
              <PickerRow active={isActive} checked={skill.isMcp ? undefined : !isDisabled}>
                {`${skill.name}  ${scopeLabel}${isDisabled ? t(' [已禁用]', ' [disabled]') : ''}`}
              </PickerRow>
              <Box paddingLeft={2}>
                <Text color={colors.content.secondary} wrap="truncate-end">
                  {skill.description.length > 70
                    ? skill.description.slice(0, 67) + '...'
                    : skill.description}
                </Text>
              </Box>
            </Box>
          );
        })}

        <PickerScrollHint visible={windowEnd < totalSelectable} direction="down" />
      </Box>
    );
  };

  const renderMarketplacesTab = () => {
    const mps = visibleMarketplaces;
    const start = Math.max(0, activeIndex - MAX_VISIBLE + 1);
    return (
      <Box flexDirection="column">
        <Box>
          <Text color={colors.content.secondary} wrap="truncate-end">{t('管理插件市场', 'Manage marketplaces')}</Text>
        </Box>

        {isAddingMarketplace && (
          <Box>
            <Text wrap="truncate-end">{t('仓库（owner/repo）：', 'repo (owner/repo): ')}{`${addInput}\u258b`}</Text>
          </Box>
        )}

        {/* "+ Add Marketplace" row */}
        {start === 0 && <PickerRow active={activeIndex === 0}>{t('+ 添加市场', '+ Add Marketplace')}</PickerRow>}
        <PickerScrollHint visible={start > 0} direction="up" />

        {mps.slice(Math.max(0, start - 1), start + MAX_VISIBLE - 1).map((mp, i) => {
          const rowIdx = Math.max(0, start - 1) + i + 1;
          const isActive = rowIdx === activeIndex;
          const isUpdating = pendingMsg.startsWith(`正在从“${mp.name}”获取技能`) ||
            pendingMsg.startsWith(`Fetching skills from '${mp.name}'`);
          return (
            <Box key={mp.name} flexDirection="column">
              <PickerRow active={isActive}>{mp.name}</PickerRow>
              <Box paddingLeft={2} flexDirection="column">
                <Text color={colors.content.secondary} wrap="truncate-end">{mp.repo}</Text>
                {isUpdating ? (
                  <Text color={colors.content.secondary} wrap="truncate-end">{t('⧗ 正在获取技能列表…', '⧗ Fetching skill list...')}</Text>
                ) : (
                  <Text color={colors.content.secondary} wrap="truncate-end">
                    {t(`${mp.available} 项可用 · ${mp.installed} 项已安装${mp.updatedAt ? ` · 更新于 ${mp.updatedAt}` : ''}`,
                      `${mp.available} available · ${mp.installed} installed${mp.updatedAt ? ` · Updated ${mp.updatedAt}` : ''}`)}
                  </Text>
                )}
              </Box>
            </Box>
          );
        })}
        <PickerScrollHint visible={start + MAX_VISIBLE < mps.length + 1} direction="down" />
      </Box>
    );
  };


  const renderFooter = () => {
    const tabName: TabName = TABS[activeTab];
    let hint: string;
    if (isAddingMarketplace) {
      hint = t('Enter 添加 · Esc 返回 · 输入仓库（owner/repo）',
        'Enter add · Esc back · Type owner/repo');
    } else if (isSearching) {
      hint = t('Enter 确定 · Esc 返回 · 输入关键词搜索',
        'Enter confirm · Esc back · Type to search');
    } else if (tabName === 'Discover') {
      hint = t('↑↓ 选择 · Esc 返回 · ←→/Tab 标签 · Space/Enter 安装/卸载 · / 搜索',
        '↑↓ select · Esc back · ←→/Tab tabs · Space/Enter install/remove · / search');
    } else if (tabName === 'Installed') {
      hint = t('↑↓ 选择 · Esc 返回 · ←→/Tab 标签 · d 启停 · r 卸载',
        '↑↓ select · Esc back · ←→/Tab tabs · d enable/disable · r remove');
    } else if (tabName === 'Marketplaces') {
      hint = t('↑↓ 选择 · Esc 返回 · ←→/Tab 标签 · Enter 添加 · u 更新 · r 移除',
        '↑↓ select · Esc back · ←→/Tab tabs · Enter add · u update · r remove');
    } else {
      hint = PANEL_TIPS.pluginDefault; // fallback
    }
    return (
      <PickerFooter>{hint}</PickerFooter>
    );
  };

  const renderContent = () => {
    const tabName: TabName = TABS[activeTab];
    if (tabName === 'Discover') return renderDiscoverTab();
    if (tabName === 'Installed') return renderInstalledTab();
    return renderMarketplacesTab();
  };

  return (
    <Box flexDirection="column" paddingX={1} width="100%">
      {renderTabBar()}
      {renderContent()}
      {renderFooter()}
    </Box>
  );
};
