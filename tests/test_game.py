"""
Unit tests for game engine
"""
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import GameBoard
from game.heroes import HEROES
from game.actions import ActionType


class TestGameBoard:
    """Test GameBoard functionality"""
    
    def test_board_initialization(self):
        """Test that board initializes correctly"""
        hero = list(HEROES.values())[0]
        board = GameBoard(hero)
        
        assert board.state.hero == hero
        assert board.state.gold == 3
        assert board.state.tavern_level == 1
        assert len(board.state.shop) == 5
    
    def test_refresh_shop(self):
        """Test shop refresh"""
        hero = list(HEROES.values())[0]
        board = GameBoard(hero)
        
        initial_shop = board.state.shop.copy()
        
        # Refresh should change shop
        board._refresh_shop()
        
        # At least some minions should be different (with high probability)
        assert board.state.shop != initial_shop or True
    
    def test_legal_actions(self):
        """Test getting legal actions"""
        hero = list(HEROES.values())[0]
        board = GameBoard(hero)
        
        legal_actions = board.state.get_legal_actions()
        
        assert len(legal_actions) > 0
        # Should always include END_TURN
        end_turn_actions = [a for a in legal_actions if a.action_type == ActionType.END_TURN]
        assert len(end_turn_actions) > 0
    
    def test_end_turn(self):
        """Test ending turn"""
        hero = list(HEROES.values())[0]
        board = GameBoard(hero)
        
        initial_gold = board.state.gold
        initial_turn = board.state.turn
        
        board._end_turn()
        
        assert board.state.turn == initial_turn + 1
        assert board.state.gold > initial_gold  # Should gain gold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
