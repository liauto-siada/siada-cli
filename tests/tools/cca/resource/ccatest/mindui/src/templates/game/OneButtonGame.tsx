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

const OneButtonGame = () => {
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
      <div className="flex-1 w-[809px] min-h-0">
      </div>

      {/* 底部控制按钮区域，用来控制游戏的开始、暂停、继续游戏和结束 */}
      <div className="w-[809px] py-4 flex-shrink-0">
        {!gameState.isPlaying ? (
          <Button
            variant="secondary"
            size="lg"
            onClick={startGame}
            className="w-full"
          >
            开始游戏
          </Button>
        ) : (
          <div className="flex w-full gap-[30px]">
            <Button
              variant="secondary"
              size="lg"
              onClick={gameState.isPaused ? resumeGame : pauseGame}
              className="flex-1"
            >
              {gameState.isPaused ? '继续游戏' : '暂停'}
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={endGame}
              className="flex-1"
            >
              结束
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

export default OneButtonGame;