"""Simple tank battle game with infinite randomly generated levels.

The game uses pygame to render a top-down battlefield.  The player controls
a tank with the arrow keys (or WASD) and shoots shells with the space bar.
Each level spawns a number of enemy tanks and a procedurally generated map
layout that includes destructible walls.  When all enemies are defeated the
level counter increments, the difficulty increases, and a new map is
generated.

This script is intentionally compact but demonstrates how to stitch together
basic game systems: entity updates, collision detection, projectile physics,
and simple state transitions between levels.  It should serve as a playable
prototype that can be extended with more advanced behaviours, art assets, or
sound effects.

Controls
========
* Arrow keys / WASD — Move and rotate the player tank.
* Space           — Fire a shell.
* Escape          — Quit the game.

Dependencies
============
```
pip install pygame
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import List, Optional, Tuple

import pygame


# --- Core constants -------------------------------------------------------

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 720
FPS = 60

TILE_SIZE = 48
GRID_WIDTH = SCREEN_WIDTH // TILE_SIZE
GRID_HEIGHT = SCREEN_HEIGHT // TILE_SIZE

PLAYER_SPEED = 180  # pixels per second
PLAYER_ROTATION_SPEED = 180  # degrees per second
ENEMY_SPEED = 120
ENEMY_ROTATION_SPEED = 120
SHELL_SPEED = 400
SHELL_COOLDOWN = 0.6

LEVEL_BASE_ENEMIES = 2
LEVEL_ENEMY_SCALE = 1.25

COLORS = {
    "background": (25, 30, 40),
    "wall": (110, 110, 110),
    "player": (80, 200, 120),
    "enemy": (200, 80, 80),
    "shell": (250, 230, 100),
    "text": (235, 235, 235),
}


# --- Utility functions ----------------------------------------------------


def vec_from_angle(angle_degrees: float) -> pygame.Vector2:
    radians = math.radians(angle_degrees)
    return pygame.Vector2(math.cos(radians), math.sin(radians))


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


# --- Game entities --------------------------------------------------------


@dataclass
class Shell:
    position: pygame.Vector2
    velocity: pygame.Vector2
    owner: "Tank"
    radius: float = 6
    alive: bool = True

    def update(self, dt: float, walls: List[pygame.Rect]) -> None:
        if not self.alive:
            return

        self.position += self.velocity * dt
        for wall in walls:
            if wall.collidepoint(self.position.x, self.position.y):
                self.alive = False
                break

        if not (0 <= self.position.x <= SCREEN_WIDTH and 0 <= self.position.y <= SCREEN_HEIGHT):
            self.alive = False

    def draw(self, surface: pygame.Surface) -> None:
        if self.alive:
            pygame.draw.circle(surface, COLORS["shell"], (int(self.position.x), int(self.position.y)), self.radius)


@dataclass
class Tank:
    position: pygame.Vector2
    angle: float
    color: Tuple[int, int, int]
    speed: float
    rotation_speed: float
    is_player: bool = False
    reload_time: float = 0.0
    shell_cooldown: float = SHELL_COOLDOWN
    shells: List[Shell] = field(default_factory=list)
    size: Tuple[int, int] = (36, 36)
    alive: bool = True

    def update(self, dt: float, level: "Level") -> None:
        if self.alive:
            self.reload_time = clamp(self.reload_time - dt, 0, self.shell_cooldown)

            if self.is_player:
                self._update_player(dt, level)
            else:
                self._update_enemy(dt, level)

            self._handle_wall_collisions(level.walls)

        for shell in self.shells:
            shell.update(dt, level.walls)
        self.shells[:] = [shell for shell in self.shells if shell.alive]

    def _update_player(self, dt: float, level: "Level") -> None:
        keys = pygame.key.get_pressed()
        move_vector = pygame.Vector2(0, 0)

        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_vector += vec_from_angle(self.angle)
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_vector -= vec_from_angle(self.angle)

        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.angle -= self.rotation_speed * dt
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.angle += self.rotation_speed * dt

        if move_vector.length_squared() > 0:
            move_vector = move_vector.normalize() * self.speed * dt
            self.position += move_vector

    def _update_enemy(self, dt: float, level: "Level") -> None:
        player = level.player
        direction = (player.position - self.position)
        if direction.length_squared() > 1:
            desired_angle = math.degrees(math.atan2(direction.y, direction.x))
            angle_delta = (desired_angle - self.angle + 180) % 360 - 180
            self.angle += clamp(angle_delta, -self.rotation_speed * dt, self.rotation_speed * dt)

        distance = direction.length()
        if distance > TILE_SIZE * 1.5:
            velocity = vec_from_angle(self.angle) * self.speed * dt
            self.position += velocity

        if distance < SCREEN_WIDTH and self.reload_time <= 0:
            self.fire()

    def _handle_wall_collisions(self, walls: List[pygame.Rect]) -> None:
        rect = self.rect
        if rect is None:
            return
        for wall in walls:
            if rect.colliderect(wall):
                dx_left = wall.right - rect.left
                dx_right = rect.right - wall.left
                dy_top = wall.bottom - rect.top
                dy_bottom = rect.bottom - wall.top
                min_penetration = min(dx_left, dx_right, dy_top, dy_bottom)

                if min_penetration == dx_left:
                    self.position.x += dx_left
                elif min_penetration == dx_right:
                    self.position.x -= dx_right
                elif min_penetration == dy_top:
                    self.position.y += dy_top
                else:
                    self.position.y -= dy_bottom
                rect = self.rect  # Recompute rect after resolving
                if rect is None:
                    return

    def fire(self) -> None:
        if self.reload_time > 0 or not self.alive:
            return
        direction = vec_from_angle(self.angle)
        shell_position = self.position + direction * (self.size[0] // 2)
        shell_velocity = direction * SHELL_SPEED
        shell = Shell(shell_position, shell_velocity, owner=self)
        self.shells.append(shell)
        self.reload_time = self.shell_cooldown

    @property
    def rect(self) -> Optional[pygame.Rect]:
        width, height = self.size
        if width == 0 or height == 0 or not self.alive:
            return None
        return pygame.Rect(int(self.position.x - width / 2), int(self.position.y - height / 2), width, height)

    def draw(self, surface: pygame.Surface) -> None:
        rect = self.rect
        if rect is None:
            return
        pygame.draw.rect(surface, self.color, rect, border_radius=6)
        barrel_length = self.size[0] // 2 + 10
        barrel_end = self.position + vec_from_angle(self.angle) * barrel_length
        start_pos = (int(self.position.x), int(self.position.y))
        end_pos = (int(barrel_end.x), int(barrel_end.y))
        pygame.draw.line(surface, COLORS["shell"], start_pos, end_pos, 4)

        for shell in self.shells:
            shell.draw(surface)


class Level:
    def __init__(self, number: int) -> None:
        self.number = number
        self.walls: List[pygame.Rect] = []
        self.enemies: List[Tank] = []
        self.player: Tank = Tank(
            position=pygame.Vector2(SCREEN_WIDTH / 2, SCREEN_HEIGHT - TILE_SIZE * 1.5),
            angle=-90,
            color=COLORS["player"],
            speed=PLAYER_SPEED,
            rotation_speed=PLAYER_ROTATION_SPEED,
            is_player=True,
        )
        self.player_destroyed = False
        self.generate_map()
        self.spawn_enemies()

    def generate_map(self) -> None:
        self.walls.clear()
        rng = random.Random(self.number)
        for y in range(1, GRID_HEIGHT - 1):
            for x in range(GRID_WIDTH):
                if rng.random() < 0.12:
                    rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
                    self.walls.append(rect)

        for x in range(GRID_WIDTH):
            self.walls.append(pygame.Rect(x * TILE_SIZE, 0, TILE_SIZE, TILE_SIZE))
            self.walls.append(pygame.Rect(x * TILE_SIZE, (GRID_HEIGHT - 1) * TILE_SIZE, TILE_SIZE, TILE_SIZE))
        for y in range(GRID_HEIGHT):
            self.walls.append(pygame.Rect(0, y * TILE_SIZE, TILE_SIZE, TILE_SIZE))
            self.walls.append(pygame.Rect((GRID_WIDTH - 1) * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE))

        self._carve_player_spawn()

    def _carve_player_spawn(self) -> None:
        safe_radius = 2
        safe_tiles = []
        player_tile_x = int(self.player.position.x // TILE_SIZE)
        player_tile_y = int(self.player.position.y // TILE_SIZE)
        for dy in range(-safe_radius, safe_radius + 1):
            for dx in range(-safe_radius, safe_radius + 1):
                tile_x = max(0, min(GRID_WIDTH - 1, player_tile_x + dx))
                tile_y = max(0, min(GRID_HEIGHT - 1, player_tile_y + dy))
                safe_tiles.append((tile_x, tile_y))

        def is_safe(rect: pygame.Rect) -> bool:
            tile_x = rect.x // TILE_SIZE
            tile_y = rect.y // TILE_SIZE
            if tile_x in (0, GRID_WIDTH - 1) or tile_y in (0, GRID_HEIGHT - 1):
                return False
            return (tile_x, tile_y) in safe_tiles

        self.walls = [wall for wall in self.walls if not is_safe(wall)]

    def spawn_enemies(self) -> None:
        enemy_count = int(LEVEL_BASE_ENEMIES + (self.number - 1) * LEVEL_ENEMY_SCALE)
        rng = random.Random(self.number * 31 + 7)
        for _ in range(enemy_count):
            for _attempt in range(100):
                x = rng.randint(1, GRID_WIDTH - 2)
                y = rng.randint(1, GRID_HEIGHT // 2)
                position = pygame.Vector2(x * TILE_SIZE + TILE_SIZE / 2, y * TILE_SIZE + TILE_SIZE / 2)
                rect = pygame.Rect(position.x - 24, position.y - 24, 48, 48)
                if not any(rect.colliderect(wall) for wall in self.walls):
                    enemy = Tank(position, 90, COLORS["enemy"], ENEMY_SPEED, ENEMY_ROTATION_SPEED)
                    self.enemies.append(enemy)
                    break

    def update(self, dt: float) -> bool:
        self.player.update(dt, self)
        for enemy in self.enemies:
            enemy.update(dt, self)

        self._handle_shell_collisions()
        self.enemies = [enemy for enemy in self.enemies if enemy.alive]
        self.player_destroyed = not self.player.alive
        return len(self.enemies) == 0 and self.player.alive

    def _handle_shell_collisions(self) -> None:
        for tank in [self.player] + self.enemies:
            for shell in list(tank.shells):
                if not shell.alive:
                    continue
                for target in [self.player] + self.enemies:
                    if target is shell.owner:
                        continue
                    rect = target.rect
                    if rect and rect.collidepoint(shell.position.x, shell.position.y):
                        shell.alive = False
                        target.alive = False
                        break

    def draw(self, surface: pygame.Surface) -> None:
        for wall in self.walls:
            pygame.draw.rect(surface, COLORS["wall"], wall)
        for enemy in self.enemies:
            enemy.draw(surface)
        self.player.draw(surface)


# --- Game loop ------------------------------------------------------------


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Tank Battle Infinite")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 24)
        self.level_number = 1
        self.level = Level(self.level_number)
        self.running = True

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.level.player.fire()

    def _update(self, dt: float) -> None:
        level_complete = self.level.update(dt)
        if level_complete:
            self.level_number += 1
            self.level = Level(self.level_number)
        elif self.level.player_destroyed:
            self.level_number = 1
            self.level = Level(self.level_number)

    def _draw(self) -> None:
        self.screen.fill(COLORS["background"])
        self.level.draw(self.screen)
        level_text = self.font.render(f"Level {self.level_number}", True, COLORS["text"])
        self.screen.blit(level_text, (10, 10))
        pygame.display.flip()


def main() -> None:
    Game().run()


if __name__ == "__main__":
    main()
