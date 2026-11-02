// scripts/patch-obsidian-headless.js
const fs = require('fs');
const path = require('path');

function patchFile(filePath) {
    if (!fs.existsSync(filePath)) {
        return false;
    }

    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    // Patch A: Fix lock time verification float / filesystem rounding error
    const targetA = 'verify(){return this.lockTime===this.get()}';
    const replaceA = 'verify(){return Math.abs(this.lockTime-this.get())<100}';
    if (content.includes(targetA)) {
        content = content.replace(targetA, replaceA);
        modified = true;
        console.log(`[patch] Applied Patch A (lock verification precision) to ${filePath}`);
    } else if (content.includes(replaceA)) {
        console.log(`[patch] Patch A already applied to ${filePath}`);
    } else {
        console.warn(`[patch] Warning: Target A not found in ${filePath}`);
    }

    // Patch B: Fix ob sync one-shot mode (do not hang forever if not --continuous)
    const targetB = 'await this.requestSync(),await e';
    const replaceB = 'await this.requestSync(),(this.continuous?await e:this.stop())';
    if (content.includes(targetB)) {
        content = content.replace(targetB, replaceB);
        modified = true;
        console.log(`[patch] Applied Patch B (one-shot sync termination) to ${filePath}`);
    } else if (content.includes(replaceB)) {
        console.log(`[patch] Patch B already applied to ${filePath}`);
    } else {
        console.warn(`[patch] Warning: Target B not found in ${filePath}`);
    }

    if (modified) {
        fs.writeFileSync(filePath, content, 'utf8');
        console.log(`[patch] Successfully saved patched file: ${filePath}`);
        return true;
    }
    return false;
}

function findCliJsFiles(dir) {
    const results = [];
    if (!fs.existsSync(dir)) return results;

    function walk(curr) {
        try {
            const list = fs.readdirSync(curr, { withFileTypes: true });
            for (const item of list) {
                const fullPath = path.join(curr, item.name);
                if (item.isDirectory()) {
                    if (item.name === 'obsidian-headless') {
                        const target = path.join(fullPath, 'cli.js');
                        if (fs.existsSync(target)) results.push(target);
                    } else if (item.name !== '.git') {
                        walk(fullPath);
                    }
                }
            }
        } catch (e) {
            // Ignore permission / access errors
        }
    }

    walk(dir);
    return results;
}

const nodeModulesDir = path.join(__dirname, '../node_modules');
const targets = findCliJsFiles(nodeModulesDir);

let totalPatched = 0;
for (const target of targets) {
    if (patchFile(target)) {
        totalPatched++;
    }
}
console.log(`[patch] Done. Patched ${totalPatched} of ${targets.length} file(s).`);
