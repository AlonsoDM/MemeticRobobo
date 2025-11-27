from robobopy.Robobo import Robobo
import random
import time

# AGGRESSIVE delays to prevent simulator overload
COMMAND_DELAY = 0.5
SENSOR_DELAY = 0.7
MOVEMENT_DELAY = 1.0

# Sensor thresholds - ADJUSTED for your simulator's high values
SENSOR_CRITICAL = 50000   # Too close - must stop
SENSOR_WARNING = 30000    # Getting close - should turn
SENSOR_SAFE = 10000       # Safe distance

# Simple Gene: represents a movement action
class MovementGene:
    def __init__(self, left_speed=None, right_speed=None, duration=None):
        # Start with more diverse movements including turns
        if left_speed is None:
            # 50% chance of differential speeds (turning)
            if random.random() < 0.5:
                self.left_speed = random.randint(30, 80)
                self.right_speed = random.randint(-20, 40)  # Allow one wheel slower/reverse
            else:
                self.left_speed = random.randint(30, 80)
                self.right_speed = random.randint(30, 80)
        else:
            self.left_speed = left_speed
            
        if right_speed is None:
            self.right_speed = self.left_speed if left_speed is not None else random.randint(30, 80)
        else:
            self.right_speed = right_speed
            
        self.duration = duration if duration is not None else random.uniform(0.8, 2.0)
    
    def mutate(self, mutation_rate=0.3):
        """Mutate this gene"""
        if random.random() < mutation_rate:
            self.left_speed = max(-50, min(100, self.left_speed + random.randint(-30, 30)))
        if random.random() < mutation_rate:
            self.right_speed = max(-50, min(100, self.right_speed + random.randint(-30, 30)))
        if random.random() < mutation_rate:
            self.duration = max(0.5, min(2.5, self.duration + random.uniform(-0.5, 0.5)))

# Individual: a sequence of movement genes
class Individual:
    def __init__(self, genome_size=5):
        self.genome = [MovementGene() for _ in range(genome_size)]
        self.fitness = 0
        self.collision_count = 0
        self.steps_completed = 0
    
    def local_search(self, rob):
        """Memetic component: refine movements to avoid obstacles"""
        rob.wait(SENSOR_DELAY)
        irs = rob.readAllIRSensor()
        rob.wait(SENSOR_DELAY)
        
        if not irs:
            return
            
        # Get max front sensor reading
        front_readings = [value for key, value in irs.items() if 'Front' in str(key)]
        if not front_readings:
            return
            
        max_reading = max(front_readings)
        
        # If currently facing obstacle, modify genes to encourage turning
        if max_reading > SENSOR_WARNING:
            print(f"  Local search: Obstacle detected ({max_reading}), adjusting genes for turning")
            for gene in self.genome:
                # Create turning behavior by making wheel speeds different
                if random.random() < 0.7:
                    # Make one wheel much slower or reverse
                    if random.random() < 0.5:
                        gene.left_speed = random.randint(50, 80)
                        gene.right_speed = random.randint(-30, 20)
                    else:
                        gene.right_speed = random.randint(50, 80)
                        gene.left_speed = random.randint(-30, 20)
                    
                    # Shorter duration for turns
                    gene.duration = min(gene.duration, 1.5)
    
    def crossover(self, other):
        """Single-point crossover"""
        point = random.randint(1, len(self.genome) - 1)
        child1 = Individual(0)
        child2 = Individual(0)
        child1.genome = self.genome[:point] + other.genome[point:]
        child2.genome = other.genome[:point] + self.genome[point:]
        return child1, child2
    
    def mutate(self):
        """Mutate the genome"""
        for gene in self.genome:
            gene.mutate()

def get_front_sensor_reading(rob):
    """Helper to get front sensor reading"""
    rob.wait(SENSOR_DELAY)
    irs = rob.readAllIRSensor()
    rob.wait(SENSOR_DELAY)
    
    if not irs:
        return 0
    
    front_readings = [value for key, value in irs.items() if 'Front' in str(key)]
    return max(front_readings) if front_readings else 0

def reset_robot_position(rob):
    """Try to move robot back from wall"""
    print("  Resetting robot position...")
    rob.wait(COMMAND_DELAY)
    # Move backward
    rob.moveWheelsByTime(-40, -40, 1.5, wait=True)
    rob.wait(MOVEMENT_DELAY)
    # Turn slightly
    rob.moveWheelsByTime(50, -50, 1.0, wait=True)
    rob.wait(MOVEMENT_DELAY)
    rob.stopMotors()
    rob.wait(COMMAND_DELAY)

def evaluate_fitness(rob, individual):
    """
    FITNESS FUNCTION focused on collision avoidance:
    - Rewards completing movement steps without collision
    - Rewards maintaining safe distance from obstacles
    - Heavily penalizes getting too close
    - Rewards turning when obstacle detected
    """
    fitness = 0
    safe_steps = 0
    total_safe_distance = 0
    
    individual.collision_count = 0
    individual.steps_completed = 0
    
    for i, gene in enumerate(individual.genome):
        # Check sensors before movement
        sensor_reading = get_front_sensor_reading(rob)
        
        # If critically close, stop evaluation
        if sensor_reading > SENSOR_CRITICAL:
            print(f"  [Gene {i+1}] BLOCKED - Obstacle too close ({sensor_reading:.0f})")
            individual.collision_count += 1
            break
        
        # Warn if getting close
        if sensor_reading > SENSOR_WARNING:
            print(f"  [Gene {i+1}] Warning - Approaching obstacle ({sensor_reading:.0f})")
        
        # Execute movement
        rob.wait(COMMAND_DELAY)
        print(f"  [Gene {i+1}] Moving: L={gene.left_speed}, R={gene.right_speed}, T={gene.duration:.1f}s")
        rob.moveWheelsByTime(gene.right_speed, gene.left_speed, gene.duration, wait=True)
        rob.wait(MOVEMENT_DELAY)
        
        individual.steps_completed += 1
        
        # Check sensors after movement
        sensor_reading_after = get_front_sensor_reading(rob)
        
        # Calculate fitness for this step
        step_fitness = 0
        
        # Base reward for completing the step
        step_fitness += 20
        
        # Reward based on final sensor reading (safer = better)
        if sensor_reading_after < SENSOR_SAFE:
            step_fitness += 30  # Clear path bonus
            safe_steps += 1
            total_safe_distance += (SENSOR_SAFE - sensor_reading_after) / 1000
            print(f"  [Gene {i+1}] Safe distance maintained")
        elif sensor_reading_after < SENSOR_WARNING:
            step_fitness += 10  # Acceptable distance
        else:
            step_fitness -= 20  # Too close - penalty
            print(f"  [Gene {i+1}] Ending too close to obstacle")
        
        # Reward turning behavior (helps avoid obstacles)
        speed_diff = abs(gene.left_speed - gene.right_speed)
        if speed_diff > 30:
            step_fitness += 15  # Turning bonus
            print(f"  [Gene {i+1}] + Turning bonus")
        
        # Movement quality bonus
        if gene.left_speed > 0 or gene.right_speed > 0:
            avg_speed = (abs(gene.left_speed) + abs(gene.right_speed)) / 2
            step_fitness += avg_speed * 0.1  # Small speed bonus
        
        fitness += step_fitness
        
        # Check if collision occurred
        if sensor_reading_after > SENSOR_CRITICAL:
            print(f"  [Gene {i+1}] COLLISION ({sensor_reading_after:.0f})")
            individual.collision_count += 1
            fitness *= 0.2  # Massive penalty for collision
            break
    
    # Bonus for completing all steps without collision
    if individual.steps_completed == len(individual.genome) and individual.collision_count == 0:
        fitness += 100
        print(f"COMPLETION BONUS: All steps completed safely!")
    
    # Bonus for safe steps
    fitness += safe_steps * 10
    
    rob.wait(COMMAND_DELAY)
    rob.stopMotors()
    rob.wait(MOVEMENT_DELAY)
    
    # Reset robot if it got too close
    sensor_final = get_front_sensor_reading(rob)
    if sensor_final > SENSOR_WARNING:
        reset_robot_position(rob)
    
    return max(0, fitness)

def memetic_algorithm(rob, population_size=4, generations=4, genome_size=4):
    """
    Memetic Algorithm for collision-avoiding robot navigation
    """
    print("=== Memetic Algorithm: Collision Avoidance ===")
    print(f"Population: {population_size}, Generations: {generations}, Genome size: {genome_size}")
    print(f"\nSensor Thresholds:")
    print(f"  Safe: < {SENSOR_SAFE}")
    print(f"  Warning: < {SENSOR_WARNING}")
    print(f"  Critical: < {SENSOR_CRITICAL}\n")
    
    # Initialize population with diverse movement patterns
    population = [Individual(genome_size) for _ in range(population_size)]
    
    best_fitness_history = []
    
    for gen in range(generations):
        print(f"\n{'='*60}")
        print(f"GENERATION {gen + 1}/{generations}")
        print(f"{'='*60}")
        
        # Evaluate fitness for each individual
        for i, individual in enumerate(population):
            print(f"\n--- Individual {i + 1}/{population_size} ---")
            individual.fitness = evaluate_fitness(rob, individual)
            print(f"→ Fitness: {individual.fitness:.2f} | Steps: {individual.steps_completed}/{genome_size} | Collisions: {individual.collision_count}")
            rob.wait(COMMAND_DELAY)
        
        # Sort by fitness
        population.sort(key=lambda x: x.fitness, reverse=True)
        best_fitness = population[0].fitness
        best_fitness_history.append(best_fitness)
        
        print(f"\n{'─'*60}")
        print(f"GENERATION {gen + 1} SUMMARY:")
        print(f"  Best Fitness: {best_fitness:.2f}")
        print(f"  Best Individual: {population[0].steps_completed}/{genome_size} steps, {population[0].collision_count} collisions")
        print(f"  Top 3 Fitness: {[f'{ind.fitness:.1f}' for ind in population[:3]]}")
        print(f"{'─'*60}")
        
        if gen == generations - 1:
            break
        
        # Selection: keep top 50%
        survivors = population[:population_size // 2]
        print(f"\n→ Survivors: {len(survivors)} individuals")
        
        # Crossover: create offspring
        offspring = []
        while len(offspring) < population_size - len(survivors):
            parent1 = random.choice(survivors)
            parent2 = random.choice(survivors)
            child1, child2 = parent1.crossover(parent2)
            offspring.extend([child1, child2])
        
        offspring = offspring[:population_size - len(survivors)]
        print(f"→ Offspring created: {len(offspring)}")
        
        # Mutation
        for individual in offspring:
            individual.mutate()
        print(f"→ Mutation applied")
        
        # Local search (MEMETIC COMPONENT)
        print(f"→ Applying local search to offspring...")
        for individual in offspring:
            individual.local_search(rob)
        
        rob.wait(1.0)
        
        # New population
        population = survivors + offspring
    
    # Return best individual
    population.sort(key=lambda x: x.fitness, reverse=True)
    print(f"\n{'='*60}")
    print("ALGORITHM COMPLETE")
    print(f"Best fitness achieved: {population[0].fitness:.2f}")
    print(f"Best solution: {population[0].steps_completed}/{genome_size} steps, {population[0].collision_count} collisions")
    print(f"{'='*60}\n")
    return population[0], best_fitness_history

# Main execution
if __name__ == "__main__":
    rob = Robobo("localhost")
    
    print("Connecting to Robobo simulator...")
    rob.connect()
    rob.wait(1.5)
    print("Connected!\n")
    
    try:
        # Run the memetic algorithm
        best_individual, fitness_history = memetic_algorithm(
            rob, 
            population_size=4,
            generations=4,
            genome_size=4
        )
        
        print("\n" + "="*60)
        print("EXECUTING BEST SOLUTION")
        print("="*60)
        rob.wait(1.0)
        
        for i, gene in enumerate(best_individual.genome):
            print(f"\nMove {i+1}/{len(best_individual.genome)}:")
            print(f"  Left speed: {gene.left_speed}, Right speed: {gene.right_speed}")
            print(f"  Duration: {gene.duration:.2f}s")
            
            sensor = get_front_sensor_reading(rob)
            print(f"  Sensor before: {sensor:.0f}")
            
            rob.moveWheelsByTime(gene.right_speed, gene.left_speed, gene.duration, wait=True)
            rob.wait(MOVEMENT_DELAY)
        
        print(f"\nFitness Evolution: {[f'{f:.1f}' for f in fitness_history]}")
        print("Best solution executed successfully!")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        rob.wait(COMMAND_DELAY)
        rob.stopMotors()
        rob.wait(COMMAND_DELAY)
        rob.disconnect()
        print("\nDisconnected from Robobo")