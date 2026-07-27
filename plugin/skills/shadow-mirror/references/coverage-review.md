# Coverage Review Patterns for Shadow Mirror

## The Review Phase

The proof is only as strong as its coverage. This phase answers: "Did we cast enough shadows to trust the verdict?"

## Coverage Signals

### Node Coverage

Percentage of operation tree nodes with at least one assertion.

```python
def calculate_node_coverage(operation_tree: dict, assertions: list) -> float:
    """Calculate what percentage of the operation tree is covered."""
    all_nodes = set(flatten_tree_paths(operation_tree))
    covered_nodes = set(a["node"] for a in assertions)
    
    return len(covered_nodes & all_nodes) / len(all_nodes) if all_nodes else 0

# Thresholds
# > 80%: High confidence
# 50-80%: Medium confidence, document gaps
# < 50%: Low confidence, expand instrumentation
```

### Level Coverage

Distribution of assertions across validation levels.

```python
def calculate_level_coverage(assertions: list) -> dict:
    """Check balance across functional/behavioral/performant/resilient."""
    by_level = {"functional": 0, "behavioral": 0, "performant": 0, "resilient": 0}
    
    for a in assertions:
        level = a.get("level", "functional")
        by_level[level] = by_level.get(level, 0) + 1
    
    total = sum(by_level.values())
    return {k: v / total if total else 0 for k, v in by_level.items()}

# Interpretation
# Hypothesis about correctness → weight toward functional
# Hypothesis about reliability → weight toward resilient
# Balanced coverage strengthens overall proof
```

### Branch Coverage

Percentage of cyclomatic paths exercised.

```python
def calculate_branch_coverage(cyclomatic_map: dict, execution_trace: list) -> float:
    """Determine how many decision branches were exercised."""
    all_branches = extract_branches(cyclomatic_map)
    exercised = set()
    
    for trace_entry in execution_trace:
        if trace_entry["type"] == "branch":
            exercised.add((trace_entry["node"], trace_entry["direction"]))
    
    return len(exercised) / len(all_branches) if all_branches else 0

# For hypothesis testing:
# - Must cover the branches relevant to the hypothesis
# - 100% branch coverage is ideal but often impractical
# - Document which branches are intentionally uncovered and why
```

### Assertion Density

Assertions per node—sparse coverage means weak proof.

```python
def calculate_assertion_density(assertions: list) -> dict:
    """Count assertions per node."""
    by_node = {}
    for a in assertions:
        node = a["node"]
        by_node[node] = by_node.get(node, 0) + 1
    
    return {
        "by_node": by_node,
        "min": min(by_node.values()) if by_node else 0,
        "max": max(by_node.values()) if by_node else 0,
        "mean": sum(by_node.values()) / len(by_node) if by_node else 0,
    }

# Red flags:
# - Nodes with only 1 assertion (single point of failure in proof)
# - High variance (some nodes heavily tested, others barely)
```

## Proof Quality Heuristics

### Falsifiability Check

Every assertion must be capable of failing. Tautological assertions weaken the proof.

```python
def check_falsifiability(assertions: list) -> list:
    """Identify assertions that may not be falsifiable."""
    suspicious = []
    
    for a in assertions:
        condition = a.get("condition", "")
        
        # Pattern matching for likely tautologies
        if "is not None" in condition and "or" in condition:
            suspicious.append({"assertion": a, "reason": "may always pass due to fallback"})
        if condition.strip() in ["True", "1", "pass"]:
            suspicious.append({"assertion": a, "reason": "literal always-true"})
        if "len(" in condition and ">= 0" in condition:
            suspicious.append({"assertion": a, "reason": "length always >= 0"})
    
    return suspicious

# Manual review questions:
# - Under what input would this assertion fail?
# - Have we tested that failing case to confirm the assertion can fail?
```

### Redundancy Analysis

Multiple observation angles on the same node strengthen the proof.

```python
def analyze_redundancy(assertions: list) -> dict:
    """Check if nodes are observed from multiple angles."""
    by_node = {}
    
    for a in assertions:
        node = a["node"]
        level = a["level"]
        by_node.setdefault(node, set()).add(level)
    
    redundancy = {}
    for node, levels in by_node.items():
        redundancy[node] = {
            "levels_covered": list(levels),
            "redundancy_score": len(levels) / 4,  # 4 possible levels
            "recommendation": "adequate" if len(levels) >= 2 else "add more perspectives"
        }
    
    return redundancy
```

### Edge Case Coverage

Boundary conditions from the hypothesis must be tested.

```python
def check_boundary_coverage(hypothesis: dict, assertions: list) -> dict:
    """Verify that hypothesis boundary conditions are covered."""
    boundary = hypothesis.get("boundary", {})
    passes_condition = boundary.get("passes", "")
    fails_condition = boundary.get("fails", "")
    
    found_pass_test = any(
        passes_condition.lower() in a.get("condition", "").lower() 
        for a in assertions
    )
    found_fail_test = any(
        fails_condition.lower() in a.get("condition", "").lower() 
        for a in assertions
    )
    
    return {
        "passes_boundary_tested": found_pass_test,
        "fails_boundary_tested": found_fail_test,
        "boundary_coverage": (found_pass_test and found_fail_test),
        "recommendation": None if (found_pass_test and found_fail_test) 
                          else f"Missing tests for: {'passes' if not found_pass_test else ''} {'fails' if not found_fail_test else ''}".strip()
    }
```

### Independence Check

Assertions shouldn't be tautologically dependent on each other.

```python
def check_independence(assertions: list) -> list:
    """Identify potentially dependent assertions."""
    dependencies = []
    
    # Simple heuristic: assertions on the same node with similar conditions
    by_node = {}
    for a in assertions:
        by_node.setdefault(a["node"], []).append(a)
    
    for node, node_assertions in by_node.items():
        if len(node_assertions) > 1:
            conditions = [a.get("condition", "") for a in node_assertions]
            # Check for subset relationships
            for i, c1 in enumerate(conditions):
                for j, c2 in enumerate(conditions):
                    if i != j and c1 in c2:
                        dependencies.append({
                            "node": node,
                            "assertion_1": node_assertions[i],
                            "assertion_2": node_assertions[j],
                            "reason": "condition subset relationship"
                        })
    
    return dependencies
```

## Review Report Generator

```python
def generate_review_report(
    hypothesis: dict,
    operation_tree: dict,
    assertions: list,
    execution_trace: list,
) -> dict:
    """Generate comprehensive coverage review report."""
    
    report = {
        "hypothesis": hypothesis,
        "coverage": {
            "node": calculate_node_coverage(operation_tree, assertions),
            "level": calculate_level_coverage(assertions),
            "branch": calculate_branch_coverage(operation_tree, execution_trace),
            "density": calculate_assertion_density(assertions),
        },
        "quality": {
            "falsifiability": check_falsifiability(assertions),
            "redundancy": analyze_redundancy(assertions),
            "boundary": check_boundary_coverage(hypothesis, assertions),
            "independence": check_independence(assertions),
        },
        "verdict": None,
        "confidence": None,
        "gaps": [],
        "recommendations": [],
    }
    
    # Calculate overall confidence
    node_cov = report["coverage"]["node"]
    branch_cov = report["coverage"]["branch"]
    boundary_ok = report["quality"]["boundary"]["boundary_coverage"]
    no_tautologies = len(report["quality"]["falsifiability"]) == 0
    
    confidence_score = (
        node_cov * 0.3 +
        branch_cov * 0.3 +
        (1.0 if boundary_ok else 0.0) * 0.2 +
        (1.0 if no_tautologies else 0.5) * 0.2
    )
    
    report["confidence"] = {
        "score": confidence_score,
        "level": "high" if confidence_score > 0.8 else "medium" if confidence_score > 0.5 else "low"
    }
    
    # Generate recommendations
    if node_cov < 0.8:
        report["recommendations"].append(f"Increase node coverage from {node_cov:.0%} to >80%")
    if not boundary_ok:
        report["recommendations"].append("Add tests for hypothesis boundary conditions")
    if report["quality"]["falsifiability"]:
        report["recommendations"].append("Review potentially tautological assertions")
    
    return report
```

## Iteration Triggers

### When to Expand Instrumentation

```python
def should_expand_instrumentation(review_report: dict) -> tuple[bool, list]:
    """Determine if more instrumentation is needed."""
    reasons = []
    
    if review_report["coverage"]["node"] < 0.8:
        reasons.append("node_coverage_low")
    if review_report["coverage"]["branch"] < 0.6:
        reasons.append("branch_coverage_low")
    if not review_report["quality"]["boundary"]["boundary_coverage"]:
        reasons.append("boundary_not_covered")
    if review_report["confidence"]["level"] == "low":
        reasons.append("overall_confidence_low")
    
    return (len(reasons) > 0, reasons)
```

### When to Refine Hypothesis

```python
def should_refine_hypothesis(assertions: list, execution_results: dict) -> tuple[bool, str]:
    """Determine if hypothesis needs refinement based on evidence."""
    
    passed = sum(1 for a in assertions if a.get("outcome") == "passed")
    failed = sum(1 for a in assertions if a.get("outcome") == "failed")
    
    if failed == 0 and passed > 0:
        return (False, "hypothesis_supported")
    
    if failed > passed:
        return (True, "evidence_contradicts_hypothesis")
    
    if failed > 0 and passed > 0:
        # Partial support—hypothesis may be incomplete
        failed_nodes = [a["node"] for a in assertions if a.get("outcome") == "failed"]
        return (True, f"hypothesis_incomplete—failures at: {failed_nodes}")
    
    return (False, "insufficient_evidence")
```

## Verdict Determination

```python
def determine_verdict(review_report: dict, assertions: list) -> dict:
    """Determine final verdict based on evidence and coverage."""
    
    passed = sum(1 for a in assertions if a.get("outcome") == "passed")
    failed = sum(1 for a in assertions if a.get("outcome") == "failed")
    total = len(assertions)
    confidence = review_report["confidence"]["level"]
    
    if confidence == "low":
        return {
            "verdict": "inconclusive",
            "reason": "insufficient coverage to determine",
            "recommendation": "expand instrumentation before concluding"
        }
    
    if failed == 0 and passed == total:
        return {
            "verdict": "proven",
            "reason": f"all {total} assertions passed with {confidence} confidence",
            "recommendation": "archive as regression suite"
        }
    
    if failed > 0:
        failed_assertions = [a for a in assertions if a.get("outcome") == "failed"]
        return {
            "verdict": "disproven",
            "reason": f"{failed}/{total} assertions failed",
            "failed_nodes": [a["node"] for a in failed_assertions],
            "recommendation": "form new hypothesis from failure evidence"
        }
    
    return {
        "verdict": "inconclusive",
        "reason": "unexpected state",
        "recommendation": "manual review required"
    }
```
