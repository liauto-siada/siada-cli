import React, { useState } from 'react';
import { Button } from '@/components/ui/button';

interface GameState {
  playerScore: number;
  opponentScore: number;
  currentRound: number;
  totalRounds: number;
  isGameOver: boolean;
  isPlaying: boolean;
  isPaused: boolean;
}

const MultiButtonGame = () => {
  const [gameState, setGameState] = useState<GameState>({
    playerScore: 5,
    opponentScore: 5,
    currentRound: 1,
    totalRounds: 10,
    isGameOver: false,
    isPlaying: false,
    isPaused: false,
  });

  // 开始游戏
  const startGame = () => {
    setGameState(prevState => ({
      ...prevState,
      isPlaying: true,
      isGameOver: false,
      isPaused: false,
    }));
  };

  // 暂停游戏
  const pauseGame = () => {
    setGameState(prevState => ({
      ...prevState,
      isPaused: true,
    }));
  };

  // 继续游戏
  const resumeGame = () => {
    setGameState(prevState => ({
      ...prevState,
      isPaused: false,
    }));
  };

  // 结束游戏
  const endGame = () => {
    setGameState(prevState => ({
      ...prevState,
      isPlaying: false,
      isGameOver: true,
      isPaused: false,
    }));
  };

  // 重新开始游戏
  const restartGame = () => {
    setGameState({
      playerScore: 5,
      opponentScore: 5,
      currentRound: 1,
      totalRounds: 10,
      isGameOver: false,
      isPlaying: false,
      isPaused: false,
    });
  };

  // 处理游戏区域点击
  const handleGameAreaClick = () => {
    if (gameState.isPlaying && !gameState.isPaused) {
      pauseGame();
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 游戏得分显示区域 */}
      <div className="flex items-center justify-start w-[809px] py-4 flex-shrink-0">
        <div className="text-2xl flex items-center">
          <span className="text-gray-700 dark:text-gray-900">玩家得分</span>
          <span className="ml-[5px] text-gray-950 dark:text-white">{gameState.playerScore}</span>
        </div>

        <div className="mx-[14px] w-[6px] h-[6px] rounded-full bg-gray-200" />

        <div className="text-2xl flex items-center">
          <span className="text-gray-700 dark:text-gray-900">对手得分</span>
          <span className="ml-[5px] text-gray-950 dark:text-white">{gameState.opponentScore}</span>
        </div>

        <div className="mx-[14px] w-[6px] h-[6px] rounded-full bg-gray-200" />

        <div className="text-2xl flex items-center">
          <span className="text-gray-700 dark:text-gray-900">已玩</span>
          <span className="ml-[5px] text-gray-950 dark:text-white">{gameState.currentRound}/{gameState.totalRounds}</span>
        </div>
      </div>

      {/* 游戏内容区域，用来实现具体游戏的内容显示*/}
      <div 
        className="flex-1 w-[809px] flex items-center justify-center min-h-0"
        onClick={handleGameAreaClick}
      >
        {!gameState.isPlaying ? (
          <Button
            variant="secondary"
            size="lg"
            onClick={startGame}
            className="w-[360px]"
          >
            开始游戏
          </Button>
        ) : gameState.isPaused ? (
          <div className="flex flex-col items-center gap-[50px]">
            <Button
              variant="secondary"
              size="lg"
              onClick={resumeGame}
              className="w-[360px]"
            >
              继续游戏
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={endGame}
              className="w-[360px]"
            >
              结束
            </Button>
          </div>
        ) : null}
      </div>

      {/* 底部控制按钮区域，两排按钮，每排3个 */}
      <div className="w-[809px] py-4 flex-shrink-0">
        {/* 第一排按钮：发射、上、大招 */}
        <div className="flex w-full gap-[30px] mb-[30px]">
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            发射
          </Button>
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            上
          </Button>
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            大招
          </Button>
        </div>
        
        {/* 第二排按钮：左、下、右 */}
        <div className="flex w-full gap-[30px]">
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            左
          </Button>
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            下
          </Button>
          <Button
            variant="secondary"
            size="lg"
            className="flex-1"
          >
            右
          </Button>
        </div>
      </div>
    </div>
  );
};

export default MultiButtonGame;