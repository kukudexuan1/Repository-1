-- NX Open Knowledge Base Schema
-- Database: nx_open_kb

CREATE DATABASE IF NOT EXISTS `nx_open_kb` 
DEFAULT CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE `nx_open_kb`;

-- API Cards Table
-- Stores individual NX Open API references
DROP TABLE IF EXISTS `api_cards`;
CREATE TABLE `api_cards` (
  `id` VARCHAR(100) PRIMARY KEY COMMENT 'Unique API identifier',
  `module` VARCHAR(200) NOT NULL COMMENT 'NX Open module name (e.g., NXOpen.Features)',
  `class_name` VARCHAR(200) DEFAULT NULL COMMENT 'Class name (e.g., ExtrudeBuilder)',
  `method` VARCHAR(200) NOT NULL COMMENT 'Method or property name',
  `returns` VARCHAR(200) DEFAULT NULL COMMENT 'Return type',
  `parameters` JSON DEFAULT NULL COMMENT 'Array of parameter objects: [{name, type, desc, optional}]',
  `constraints` TEXT DEFAULT NULL COMMENT 'Usage constraints and preconditions',
  `example_python` TEXT DEFAULT NULL COMMENT 'Python code example',
  `related_classes` JSON DEFAULT NULL COMMENT 'Array of related class/module names',
  `tags` JSON DEFAULT NULL COMMENT 'Array of tags for categorization',
  `tags_text` TEXT DEFAULT NULL COMMENT 'Flattened tags for full-text search',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_module` (`module`),
  INDEX `idx_class` (`class_name`),
  INDEX `idx_method` (`method`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add full-text index for API cards
ALTER TABLE `api_cards`
ADD FULLTEXT INDEX `ft_api` (`module`, `class_name`, `method`, `constraints`, `tags_text`)
WITH PARSER ngram;

-- Skill Cards Table
-- Stores complete modeling workflows/skills
DROP TABLE IF EXISTS `skill_cards`;
CREATE TABLE `skill_cards` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `skill_name` VARCHAR(300) NOT NULL COMMENT 'Skill name/description',
  `required_objects` JSON DEFAULT NULL COMMENT 'Array of required preconditions',
  `steps` JSON NOT NULL COMMENT 'Array of step objects: [{step, action, api_id, note}]',
  `post_condition` TEXT DEFAULT NULL COMMENT 'Expected state after completion',
  `full_example_python` TEXT DEFAULT NULL COMMENT 'Complete working Python example',
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_skill_name` (`skill_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add full-text index for skill cards
ALTER TABLE `skill_cards`
ADD FULLTEXT INDEX `ft_skill` (`skill_name`)
WITH PARSER ngram;

-- Sample data for testing (optional)
-- Uncomment to insert sample records

/*
INSERT INTO `api_cards` (`id`, `module`, `class_name`, `method`, `returns`, `parameters`, `constraints`, `example_python`, `tags_text`) VALUES
('nx_session_get', 'NXOpen', 'Session', 'GetSession', 'Session', '[]', 'Static method, always available', 'theSession = NXOpen.Session.GetSession()', 'session core'),
('nx_part_work', 'NXOpen', 'Session', 'Parts.Work', 'Part', '[]', 'Returns current work part, may be None', 'workPart = theSession.Parts.Work', 'part work session');

INSERT INTO `skill_cards` (`skill_name`, `required_objects`, `steps`, `full_example_python`) VALUES
('获取当前工作部件', '[]', '[{"step": 1, "action": "获取Session对象", "api_id": "nx_session_get"}, {"step": 2, "action": "获取工作部件", "api_id": "nx_part_work"}]', 
'import NXOpen\n\ntry:\n    theSession = NXOpen.Session.GetSession()\n    workPart = theSession.Parts.Work\n    if workPart:\n        print(f"当前工作部件: {workPart.Name}")\nexcept Exception as e:\n    print(f"错误: {e}")');
*/
