from collections import deque

def topological_sort(commit_graph):
    """
    Perform topological sort on the commit DAG.
    Returns commits in order where parents come before children.
    """
    # Count in-degrees (number of children)
    in_degree = {sha: len(commit['children']) for sha, commit in commit_graph.items()}
    
    # Find all commits with no children (leaf nodes)
    queue = deque([sha for sha, degree in in_degree.items() if degree == 0])
    
    sorted_commits = []
    
    while queue:
        sha = queue.popleft()
        sorted_commits.append(sha)
        
        # For each parent of this commit
        commit = commit_graph[sha]
        for parent_sha in commit['parents']:
            if parent_sha in commit_graph:
                in_degree[parent_sha] -= 1
                if in_degree[parent_sha] == 0:
                    queue.append(parent_sha)
    
    return sorted_commits

def get_commit_depth(sha, commit_graph, cache=None):
    """Calculate the depth of a commit (distance from root)"""
    if cache is None:
        cache = {}
    
    if sha in cache:
        return cache[sha]
    
    commit = commit_graph.get(sha)
    if not commit or not commit['parents']:
        depth = 0
    else:
        depth = 1 + max(get_commit_depth(p, commit_graph, cache) 
                       for p in commit['parents'] if p in commit_graph)
    
    cache[sha] = depth
    return depth

def find_common_ancestor(sha1, sha2, commit_graph):
    """Find the most recent common ancestor of two commits"""
    ancestors1 = set()
    ancestors2 = set()
    
    def get_all_ancestors(sha, ancestors):
        if sha in ancestors:
            return
        ancestors.add(sha)
        commit = commit_graph.get(sha)
        if commit:
            for parent in commit['parents']:
                get_all_ancestors(parent, ancestors)
    
    get_all_ancestors(sha1, ancestors1)
    get_all_ancestors(sha2, ancestors2)
    
    common = ancestors1 & ancestors2
    
    # Find the most recent (highest depth) common ancestor
    if common:
        return max(common, key=lambda sha: get_commit_depth(sha, commit_graph))
    return None

def get_branches_containing_commit(sha, commit_graph, branch_tips):
    """Find all branches that contain this commit"""
    branches = []
    
    for branch, tip_sha in branch_tips.items():
        # Check if sha is an ancestor of the branch tip
        if is_ancestor(sha, tip_sha, commit_graph):
            branches.append(branch)
    
    return branches

def is_ancestor(potential_ancestor, sha, commit_graph):
    """Check if potential_ancestor is an ancestor of sha"""
    if potential_ancestor == sha:
        return True
    
    commit = commit_graph.get(sha)
    if not commit or not commit['parents']:
        return False
    
    for parent in commit['parents']:
        if is_ancestor(potential_ancestor, parent, commit_graph):
            return True
    
    return False
