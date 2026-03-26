/**
 * Plugin Manager Component
 * TUI for discovering, installing, and managing skills/plugins
 */

import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';

// ─── Types ─────────────────────────────────────────────────────────────────

export interface SkillInfo {
  name: string;
  description: string;
  scope: 'user' | 'repo' | 'system';
  path: string;
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
const MAX_VISIBLE = 8;

// ─── Component ─────────────────────────────────────────────────────────────

export const PluginManager: React.FC<PluginManagerProps> = ({ data, installProgress, onAction, onExit }) => {
  const { columns } = useTerminalSize();

  const [activeTab, setActiveTab] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);

  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  const [isAddingMarketplace, setIsAddingMarketplace] = useState(false);
  const [addInput, setAddInput] = useState('');

  const [localInstalled, setLocalInstalled] = useState<Set<string>>(
    () => new Set(data.installed.map(s => s.name))
  );
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

  // ─── Derived ─────────────────────────────────────────────────────────────

  const discoverSkills = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return data.discover.filter(
      s => !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
    );
  }, [data.discover, searchQuery]);

  const installedSkills = useMemo(
    () => data.installed.filter(s => !localRemovedSkills.has(s.name)),
    [data.installed, localRemovedSkills]
  );

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
          setPendingMsg(`Removing '${skill.name}'...`);
          onAction(`/plugin remove ${skill.name}`);
        } else {
          setLocalInstalled(s => new Set([...s, skill.name]));
          setPendingMsg(`Waiting for clone to start...`);
          onAction(`/plugin install ${skill.name} @${skill.marketplaceName}`);
        }
      }
    } else if (tabName === 'Installed') {
      const skill = installedSkills[activeIndex];
      if (!skill) return;
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
          setPendingMsg(`Fetching skills from '${mp.name}'...`);
          onAction(`/plugin marketplace update ${mp.name}`);
        }
      }
    }
  });

  // ─── Render helpers ───────────────────────────────────────────────────────

  const sep = '\u2500'.repeat(Math.max(10, columns - 2));

  const renderTabBar = () => (
    <Box flexDirection="column" marginBottom={1}>
      <Box flexDirection="row" paddingX={1}>
        <Text bold color="white">
          {' Plugins  '}
        </Text>
        {TABS.map((tab, i) => (
          <Text
            key={tab}
            color={activeTab === i ? 'cyan' : 'gray'}
            bold={activeTab === i}
          >
            {tab}
            {'   '}
          </Text>
        ))}
        <Text color="gray" dimColor>
          {'(\u2190/\u2192 or tab to move)'}
        </Text>
      </Box>
      <Text color="gray" dimColor>
        {sep}
      </Text>
    </Box>
  );

  const renderDiscoverTab = () => {
    const skills = discoverSkills;
    const startIdx = Math.max(0, activeIndex - MAX_VISIBLE + 1);
    const endIdx = Math.min(skills.length, startIdx + MAX_VISIBLE);
    const visible = skills.slice(startIdx, endIdx);

    return (
      <Box flexDirection="column">
        <Box paddingX={2} marginBottom={1}>
          <Text color="gray" dimColor>
            {`Discover plugins (${skills.length}/${data.discover.length})`}
          </Text>
        </Box>

        <Box paddingX={2} marginBottom={1}>
          <Box
            borderStyle="round"
            borderColor={isSearching ? 'cyan' : 'gray'}
            paddingX={1}
          >
            <Text color={isSearching ? 'cyan' : 'gray'}>
              {isSearching
                ? `\u2315 ${searchQuery}\u258b`
                : searchQuery
                ? `\u2315 ${searchQuery}`
                : '\u2315 Search\u2026'}
            </Text>
          </Box>
        </Box>

        {skills.length === 0 && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>
              {data.marketplaces.length === 0
                ? 'No marketplaces configured. Add one in the Marketplaces tab.'
                : searchQuery
                ? 'No skills match your search.'
                : 'No skills available from configured marketplaces.'}
            </Text>
          </Box>
        )}

        {visible.map((skill, relIdx) => {
          const absIdx = startIdx + relIdx;
          const isActive = absIdx === activeIndex;
          const isInstalled = localInstalled.has(skill.name);
          return (
            <Box key={skill.name} paddingX={2} flexDirection="column">
              <Box flexDirection="row">
                <Text color={isActive ? 'cyan' : 'gray'}>
                  {isActive ? '\u276f ' : '  '}
                </Text>
                <Text color={isInstalled ? 'green' : 'gray'}>
                  {isInstalled ? '\u25c9' : '\u25ef'}
                </Text>
                <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>
                  {` ${skill.name}`}
                </Text>
                <Text color="gray" dimColor>
                  {` \u00b7 ${skill.marketplaceName || skill.marketplace}${skill.installs ? ` \u00b7 ${skill.installs} installs` : ''}`}
                </Text>
              </Box>
              <Box paddingLeft={4}>
                <Text color="gray" dimColor>
                  {skill.description.length > 72
                    ? skill.description.slice(0, 69) + '...'
                    : skill.description}
                </Text>
              </Box>
            </Box>
          );
        })}

        {startIdx > 0 && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>{`\u2191 ${startIdx} more above`}</Text>
          </Box>
        )}
        {endIdx < skills.length && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>{'\u2193 more below'}</Text>
          </Box>
        )}

        {installProgress ? (() => {
          const barWidth = Math.max(20, Math.min(40, columns - 36));
          const filled = Math.round((installProgress.percent / 100) * barWidth);
          const bar = '\u2588'.repeat(filled) + '\u2591'.repeat(barWidth - filled);
          return (
            <Box paddingX={2} marginTop={1} flexDirection="column">
              <Box flexDirection="row" gap={1}>
                <Text color="yellow">{`\u29d7 ${installProgress.skillName}`}</Text>
                <Text color="gray" dimColor>{installProgress.phase}</Text>
              </Box>
              <Box flexDirection="row" gap={1}>
                <Text color="cyan">{bar}</Text>
                <Text color="white" bold>{`${installProgress.percent}%`}</Text>
              </Box>
            </Box>
          );
        })() : pendingMsg ? (
          <Box paddingX={2} marginTop={1}>
            <Text color="yellow">{`\u29d7 ${pendingMsg}`}</Text>
          </Box>
        ) : null}
      </Box>
    );
  };

  const renderInstalledTab = () => {
    const skills = installedSkills;
    const startIdx = Math.max(0, activeIndex - MAX_VISIBLE + 1);
    const endIdx = Math.min(skills.length, startIdx + MAX_VISIBLE);
    const visible = skills.slice(startIdx, endIdx);

    return (
      <Box flexDirection="column">
        <Box paddingX={2} marginBottom={1}>
          <Text color="gray" dimColor>{`Installed skills (${skills.length})`}</Text>
        </Box>

        {skills.length === 0 && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>
              No skills installed. Install from the Discover tab.
            </Text>
          </Box>
        )}

        {visible.map((skill, relIdx) => {
          const absIdx = startIdx + relIdx;
          const isActive = absIdx === activeIndex;
          const isDisabled = localDisabled.has(skill.name);
          const scopeLabel =
            skill.scope === 'user' ? '[user]' : skill.scope === 'repo' ? '[repo]' : '[system]';
          return (
            <Box key={skill.name} paddingX={2} flexDirection="column">
              <Box flexDirection="row">
                <Text color={isActive ? 'cyan' : 'gray'}>
                  {isActive ? '\u276f ' : '  '}
                </Text>
                <Text color={isDisabled ? 'gray' : isActive ? 'cyan' : 'white'}>
                  {`${isDisabled ? '\u25cb' : '\u25cf'} ${skill.name}`}
                </Text>
                <Text color="gray" dimColor>
                  {`  ${scopeLabel}${isDisabled ? '  [disabled]' : ''}`}
                </Text>
              </Box>
              <Box paddingLeft={4}>
                <Text color="gray" dimColor>
                  {skill.description.length > 72
                    ? skill.description.slice(0, 69) + '...'
                    : skill.description}
                </Text>
              </Box>
            </Box>
          );
        })}

        {startIdx > 0 && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>{`\u2191 ${startIdx} more above`}</Text>
          </Box>
        )}
        {endIdx < skills.length && (
          <Box paddingX={4}>
            <Text color="gray" dimColor>{'\u2193 more below'}</Text>
          </Box>
        )}
      </Box>
    );
  };

  const renderMarketplacesTab = () => {
    const mps = visibleMarketplaces;
    return (
      <Box flexDirection="column">
        <Box paddingX={2} marginBottom={1}>
          <Text color="gray" dimColor>Manage marketplaces</Text>
        </Box>

        {isAddingMarketplace && (
          <Box paddingX={2} marginBottom={1}>
            <Box borderStyle="round" borderColor="cyan" paddingX={1}>
              <Text color="cyan">{'repo (owner/repo): '}</Text>
              <Text color="white">{`${addInput}\u258b`}</Text>
            </Box>
          </Box>
        )}

        {/* "+ Add Marketplace" row */}
        <Box paddingX={2} flexDirection="row">
          <Text color={activeIndex === 0 ? 'cyan' : 'gray'}>
            {activeIndex === 0 ? '\u276f ' : '  '}
          </Text>
          <Text color={activeIndex === 0 ? 'cyan' : 'green'} bold>
            + Add Marketplace
          </Text>
        </Box>

        {mps.map((mp, i) => {
          const rowIdx = i + 1;
          const isActive = rowIdx === activeIndex;
          const isUpdating = pendingMsg.startsWith(`Fetching skills from '${mp.name}'`);
          return (
            <Box key={mp.name} paddingX={2} flexDirection="column" marginTop={1}>
              <Box flexDirection="row">
                <Text color={isActive ? 'cyan' : 'gray'}>
                  {isActive ? '\u276f ' : '  '}
                </Text>
                <Text color={isActive ? 'cyan' : 'white'} bold>
                  {`\u25cf ${mp.name}`}
                </Text>
              </Box>
              <Box paddingLeft={4} flexDirection="column">
                <Text color="gray" dimColor>{mp.repo}</Text>
                {isUpdating ? (
                  <Text color="yellow">{`\u29d7 Fetching skill list...`}</Text>
                ) : (
                  <Text color="gray" dimColor>
                    {`${mp.available} available \u2022 ${mp.installed} installed${mp.updatedAt ? ` \u2022 Updated ${mp.updatedAt}` : ''}`}
                  </Text>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    );
  };


  const renderFooter = () => {
    const tabName: TabName = TABS[activeTab];
    let hint: string;
    if (isAddingMarketplace) {
      hint = 'Type repo (owner/repo) · Enter to add · Esc to cancel';
    } else if (isSearching) {
      hint = 'Type to search · Enter to confirm · Esc to cancel';
    } else if (tabName === 'Discover') {
      hint = '/ to search · Space/Enter to toggle · ←/→ or tab to switch · Esc to exit';
    } else if (tabName === 'Installed') {
      hint = '↑↓ navigate · d to disable/enable · r to remove · ←/→ or tab to switch · Esc to exit';
    } else if (tabName === 'Marketplaces') {
      hint = 'Enter to add · u to update · r to remove · ←/→ or tab to switch · Esc to exit';
    } else {
      hint = '↑↓ navigate · ←/→ or tab to switch · Esc to exit'; // fallback
    }
    return (
      <Box paddingX={2} marginTop={1}>
        <Text color="gray" dimColor>
          {hint}
        </Text>
      </Box>
    );
  };

  const renderContent = () => {
    const tabName: TabName = TABS[activeTab];
    if (tabName === 'Discover') return renderDiscoverTab();
    if (tabName === 'Installed') return renderInstalledTab();
    return renderMarketplacesTab();
  };

  return (
    <Box flexDirection="column">
      {renderTabBar()}
      {renderContent()}
      {renderFooter()}
    </Box>
  );
};
